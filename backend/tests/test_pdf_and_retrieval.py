from io import BytesIO

from docx import Document
from pypdf import PdfWriter

from app.db.session import SessionLocal
from app.models import SourceChunk, TrustedSource
from app.services.documents import DocumentKind, UploadedDocument, extract_document_text, split_text
from app.services.retrieval import retrieve_sources


def test_split_text_keeps_order_and_bounds():
    text = "\n\n".join(["الحمد لله " * 20, "أما بعد " * 20, "فاتقوا الله " * 20])
    segments = split_text(text, max_chars=150)
    assert len(segments) >= 3
    assert all(len(segment) <= 150 for segment in segments)
    assert segments[0].startswith("الحمد")


def test_extracts_arabic_text_from_docx():
    output = BytesIO()
    document = Document()
    document.add_heading("خطبة الجمعة", level=1)
    document.add_paragraph("الحمد لله رب العالمين، والصلاة والسلام على رسول الله.")
    document.add_paragraph("أما بعد، فاتقوا الله عباد الله، واصبروا واشكروا.")
    document.save(output)

    text = extract_document_text(
        UploadedDocument(output.getvalue(), DocumentKind.DOCX),
        require_arabic=True,
    )

    assert "الحمد لله رب العالمين" in text
    assert "فاتقوا الله" in text


def test_scanned_pdf_uses_ocr_fallback(monkeypatch):
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(output)
    ocr_text = (
        "الحمد لله رب العالمين، نحمده ونستعينه ونستغفره. "
        "أما بعد، فاتقوا الله عباد الله واصبروا واشكروا."
    )
    monkeypatch.setattr("app.services.documents.ocr_pdf", lambda content, page_count: ocr_text)

    text = extract_document_text(
        UploadedDocument(output.getvalue(), DocumentKind.PDF),
        require_arabic=True,
        allow_ocr=True,
    )

    assert text == ocr_text


def test_retrieval_prefers_matching_trusted_chunk(seeded_accounts):
    with SessionLocal() as db:
        source = TrustedSource(
            mosque_id=seeded_accounts["mosque_id"],
            title="Approved source",
            authority="Committee",
            language="ar",
            file_path="tests/source.pdf",
            sha256="d" * 64,
        )
        db.add(source)
        db.flush()
        db.add_all(
            [
                SourceChunk(source_id=source.id, ordinal=0, text="الزكاة طهرة للمال"),
                SourceChunk(source_id=source.id, ordinal=1, text="الصبر مفتاح الفرج"),
            ]
        )
        db.commit()
        results = retrieve_sources(db, seeded_accounts["mosque_id"], "حديث عن الصبر")

    assert results[0].text == "الصبر مفتاح الفرج"
