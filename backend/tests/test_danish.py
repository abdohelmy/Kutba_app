from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from conftest import login_headers

from app.db.session import SessionLocal
from app.models import Sermon, SermonSegment, SermonStatus, VerificationStatus
from app.services.danish import assemble_danish, translation_parts
from app.services.providers.localization import DanishDraft
from app.services.providers.openai_provider import OpenAIResponsesProvider


@pytest.mark.asyncio
async def test_danish_uses_medium_without_changing_english_reasoning():
    provider = OpenAIResponsesProvider(api_key="test", model="gpt-6-luna", reasoning_effort="high")
    parse = AsyncMock(return_value=SimpleNamespace(output_parsed=object()))
    provider.client = SimpleNamespace(responses=SimpleNamespace(parse=parse))
    await provider.localize_danish({"title": "Test", "parts": [], "terms": []})
    assert parse.call_args.kwargs["reasoning"] == {"effort": "medium"}
    await provider.translate("الحمد لله", "en", [])
    assert parse.call_args.kwargs["reasoning"] == {"effort": "high"}
    await provider.verify("الحمد لله", "Praise be to Allah", "en", [])
    assert parse.call_args.kwargs["reasoning"] == {"effort": "high"}
    assert provider.reasoning_effort == "high"


def seed_english(accounts):
    with SessionLocal() as db:
        sermon = Sermon(
            mosque_id=accounts["mosque_id"], title="Peace", khutba_date=date(2026, 10, 2),
            target_language="en", source_file_path="tests/shared.pdf", source_file_sha256="a"*64,
            arabic_text="علينا بالتقوى", created_by=accounts["admin_id"],
            status=SermonStatus.PUBLISHED,
            segments=[SermonSegment(ordinal=0, arabic_text="علينا بالتقوى",
                       translated_text="Have God-consciousness (التقوى).",
                       verification_status=VerificationStatus.HUMAN_APPROVED)],
        )
        db.add(sermon)
        db.commit()
        return sermon.id


def test_danish_review_publication_and_stale_english(client, seeded_accounts):
    parent = seed_english(seeded_accounts)
    headers = login_headers(client, "admin", "correct-horse-123")
    response = client.post(f"/api/v1/admin/sermons/{parent}/danish", headers=headers)
    assert response.status_code == 200, response.text
    child = response.json()["id"]
    assert child != parent
    again = client.post(f"/api/v1/admin/sermons/{parent}/danish", headers=headers)
    assert again.json()["id"] == child
    detail = client.get(f"/api/v1/admin/sermons/{child}", headers=headers).json()
    assert detail["status"] == "REVIEW_REQUIRED", detail
    assert client.get(f"/api/v1/reader/sermons/{child}").status_code == 404
    assert client.post(f"/api/v1/admin/sermons/{child}/publish", headers=headers).status_code == 409
    segment = detail["segments"][0]
    assert client.patch(f"/api/v1/admin/sermons/{child}/segments/{segment['id']}",
                        headers=headers, json={"approved": True}).status_code == 200
    assert client.post(f"/api/v1/admin/sermons/{child}/publish", headers=headers).status_code == 200
    public = client.get(f"/api/v1/reader/sermons/{child}").json()
    assert public["target_language"] == "da"
    assert public["segments"][0]["glossary_terms"][0]["localized_phrase"].startswith("[da]")
    assert client.get(f"/api/v1/reader/sermons/{child}/pdf").status_code == 200
    with SessionLocal() as db:
        english = db.get(Sermon, parent)
        assert english.segments[0].translated_text == "Have God-consciousness (التقوى)."
        english.segments[0].translated_text += " A correction."
        db.commit()
    assert client.get(f"/api/v1/reader/sermons/{child}").status_code == 404
    listed = client.get(f"/api/v1/reader/mosques/{seeded_accounts['mosque_id']}/sermons").json()
    assert [s["id"] for s in listed] == [parent]


def test_danish_citation_offsets_are_rebuilt_and_occurrence_aware():
    text = "He said: Peace. Then: Peace."
    citations = [dict(excerpt="Peace.", translation_start=a, translation_end=a+6,
                      chunk_id="same", source_id="same", arabic_excerpt="السلام")
                 for a in (text.index("Peace."), text.rindex("Peace."))]
    parts = translation_parts(text, citations)
    values = ["Han sagde: ", "Fred.", " Så: ", "Fred."]
    draft = DanishDraft(title="Fred", parts=[dict(id=p["id"], text=v)
                                            for p, v in zip(parts, values, strict=True)], terms=[])
    result, refs, _ = assemble_danish(parts, citations, [], draft)
    assert len(refs) == 2
    assert refs[0]["translation_start"] != refs[1]["translation_start"]
    for ref in refs:
        assert result[ref["translation_start"]:ref["translation_end"]] == "Fred."
    draft.parts.reverse()
    with pytest.raises(ValueError, match="reordered"):
        assemble_danish(parts, citations, [], draft)


def test_danish_cannot_change_arabic_notes():
    parts = translation_parts("Piety (التقوى).", [])
    draft = DanishDraft(title="Fromhed", parts=[dict(id=0, text="Fromhed.")], terms=[])
    with pytest.raises(ValueError, match="Arabic glossary"):
        assemble_danish(parts, [], [], draft)


def test_danish_delete_preserves_shared_upload(client, seeded_accounts, monkeypatch):
    parent = seed_english(seeded_accounts)
    headers = login_headers(client, "admin", "correct-horse-123")
    child = client.post(f"/api/v1/admin/sermons/{parent}/danish", headers=headers).json()["id"]
    removed = []
    monkeypatch.setattr("app.api.routes.admin.remove_stored_file", removed.append)
    assert client.delete(f"/api/v1/admin/sermons/{child}", headers=headers).status_code == 204
    assert removed == []
    assert client.get(f"/api/v1/reader/sermons/{parent}").status_code == 200


def test_danish_requires_published_english(client, seeded_accounts):
    parent = seed_english(seeded_accounts)
    with SessionLocal() as db:
        db.get(Sermon, parent).status = SermonStatus.REVIEW_REQUIRED
        db.commit()
    headers = login_headers(client, "admin", "correct-horse-123")
    assert client.post(f"/api/v1/admin/sermons/{parent}/danish", headers=headers).status_code == 409
    assert client.post(f"/api/v1/admin/sermons/{parent}/danish").status_code == 401


def test_title_edit_after_publication_preserves_danish_and_content(client, seeded_accounts):
    from app.services.danish import english_is_current

    parent = seed_english(seeded_accounts)
    headers = login_headers(client, "admin", "correct-horse-123")
    child = client.post(f"/api/v1/admin/sermons/{parent}/danish", headers=headers).json()["id"]
    response = client.patch(f"/api/v1/admin/sermons/{parent}/title", headers=headers,
                            json={"title": "  A better title  "})
    assert response.status_code == 200, response.text
    assert response.json()["title"] == "A better title"
    with SessionLocal() as db:
        sermon = db.get(Sermon, parent)
        assert sermon.status == SermonStatus.PUBLISHED
        assert not sermon.title_is_inferred
        assert sermon.segments[0].translated_text == "Have God-consciousness (التقوى)."
        assert english_is_current(db.get(Sermon, child), db)
        assert db.get(Sermon, child).title != sermon.title
    for title in ("   ", "x" * 251):
        assert client.patch(f"/api/v1/admin/sermons/{parent}/title", headers=headers,
                            json={"title": title}).status_code == 422
    assert client.patch(
        f"/api/v1/admin/sermons/{parent}/title", json={"title": "No"}
    ).status_code == 401


def test_title_edit_does_not_revive_stale_danish(client, seeded_accounts):
    from app.services.danish import english_is_current

    parent = seed_english(seeded_accounts)
    headers = login_headers(client, "admin", "correct-horse-123")
    child = client.post(f"/api/v1/admin/sermons/{parent}/danish", headers=headers).json()["id"]
    with SessionLocal() as db:
        db.get(Sermon, parent).segments[0].translated_text += " Changed."
        db.commit()
    assert client.patch(f"/api/v1/admin/sermons/{parent}/title", headers=headers,
                        json={"title":"New title"}).status_code == 200
    with SessionLocal() as db:
        assert not english_is_current(db.get(Sermon, child), db)
