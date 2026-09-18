from io import BytesIO

from docx import Document

from app.db.session import SessionLocal
from app.models import Sermon

DOCX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _docx_bytes(*paragraphs: str) -> bytes:
    output = BytesIO()
    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    document.save(output)
    return output.getvalue()


def test_admin_can_upload_docx_sermon(client, seeded_accounts):
    from conftest import login_headers

    headers = login_headers(client, "admin", "correct-horse-123")
    arabic_document = _docx_bytes(
        "خطبة الجمعة: الصبر والشكر",
        "الحمد لله رب العالمين، نحمده ونستعينه ونستغفره، والصلاة والسلام على رسول الله.",
        "أما بعد، فاتقوا الله عباد الله، واصبروا واشكروا، وأحسنوا إلى الجار والمحتاج.",
    )
    sermon = client.post(
        "/api/v1/admin/sermons",
        headers=headers,
        data={
            "title": "الصبر والشكر",
            "khutba_date": "2026-08-07",
            "target_language": "en",
        },
        files={"file": ("arabic-khutba.docx", arabic_document, DOCX_MIME_TYPE)},
    )
    assert sermon.status_code == 201, sermon.text
    assert sermon.json()["status"] == "SOURCE_REVIEW_REQUIRED"

    blocked = client.post(
        f"/api/v1/admin/sermons/{sermon.json()['id']}/translate",
        headers=headers,
    )
    assert blocked.status_code == 409

    detail = client.get(
        f"/api/v1/admin/sermons/{sermon.json()['id']}",
        headers=headers,
    ).json()
    confirmed = client.put(
        f"/api/v1/admin/sermons/{sermon.json()['id']}/source-text",
        headers=headers,
        json={"arabic_text": "\n\n".join(item["arabic_text"] for item in detail["segments"])},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "DRAFT"

    with SessionLocal() as db:
        stored = db.get(Sermon, sermon.json()["id"])
        assert stored is not None
        assert stored.source_file_path.endswith(".docx")
        assert "فاتقوا الله" in stored.arabic_text


def test_admin_can_omit_title_and_get_an_inferred_heading(client, seeded_accounts):
    from conftest import login_headers

    headers = login_headers(client, "admin", "correct-horse-123")
    arabic_document = _docx_bytes(
        "خطبة الجمعة: الصبر والشكر",
        "الحمد لله رب العالمين، نحمده ونستعينه ونستغفره، والصلاة والسلام على رسول الله.",
        "أما بعد، فاتقوا الله عباد الله، واصبروا واشكروا، وأحسنوا إلى الجار والمحتاج.",
    )
    response = client.post(
        "/api/v1/admin/sermons",
        headers=headers,
        data={
            "khutba_date": "2026-08-14",
            "target_language": "en",
        },
        files={"file": ("arabic-khutba.docx", arabic_document, DOCX_MIME_TYPE)},
    )

    assert response.status_code == 201, response.text
    assert response.json()["title"] == "الصبر والشكر"
    with SessionLocal() as db:
        stored = db.get(Sermon, response.json()["id"])
        assert stored is not None
        assert stored.title_is_inferred is True


def test_rejects_sermon_whose_extension_does_not_match_content(client, seeded_accounts):
    from conftest import login_headers

    headers = login_headers(client, "admin", "correct-horse-123")
    response = client.post(
        "/api/v1/admin/sermons",
        headers=headers,
        data={
            "title": "Invalid file",
            "khutba_date": "2026-08-07",
            "target_language": "en",
        },
        files={"file": ("not-really-a-pdf.pdf", _docx_bytes("Enough text " * 20), DOCX_MIME_TYPE)},
    )

    assert response.status_code == 400
    assert "filename extension" in response.json()["detail"]
