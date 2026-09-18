from app.services.citation_edits import reanchor_citations


def citation(text, quote, start=None):
    start = text.index(quote) if start is None else start
    return {
        "chunk_id": "quran:2:152",
        "source_id": "quran.com:2:152",
        "title": "Al-Baqarah 152",
        "authority": "Quran.com",
        "source_kind": "quran",
        "excerpt": quote,
        "translation_start": start,
        "translation_end": start + len(quote),
    }


def test_edit_before_quote_moves_anchor_including_unicode():
    text = "Remember Me and I will remember you."
    result, issues = reanchor_citations(text, "A reminder ﷺ 🌙: " + text, [citation(text, text)])
    assert not issues
    assert result[0]["translation_start"] == len("A reminder ﷺ 🌙: ")


def test_edit_inside_quote_is_flagged_and_recoverable():
    text = "Remember Me and I will remember you."
    edited = text.replace("remember you", "forget you")
    result, issues = reanchor_citations(text, edited, [citation(text, text)])
    assert issues and result[0]["anchor_valid"] is False
    assert result[0]["translation_start"] is None
    restored, issues = reanchor_citations(edited, text, result)
    assert not issues and restored[0]["anchor_valid"]


def test_repeated_quotations_stay_separate_after_prefix_edit():
    quote = "Remember Me and I will remember you."
    text = quote + " Reflect upon this promise. " + quote
    citations = [citation(text, quote, 0), citation(text, quote, text.rindex(quote))]
    result, issues = reanchor_citations(text, "Introduction. " + text, citations)
    assert not issues
    assert [c["translation_start"] for c in result] == [14, 14 + text.rindex(quote)]


def test_legacy_ambiguous_quote_is_not_guessed():
    item = citation("Be patient.", "Be patient.")
    item["translation_start"] = item["translation_end"] = None
    result, issues = reanchor_citations("", "Be patient. Be patient.", [item])
    assert issues and result[0]["anchor_valid"] is False


def test_review_reanchors_and_blocks_changed_quotation(client, seeded_accounts):
    from conftest import login_headers
    from test_workflow import _seed_sermon

    from app.db.session import SessionLocal
    from app.models import Sermon, SermonStatus

    sermon_id = _seed_sermon(seeded_accounts)
    quote = "Remember Me and I will remember you."
    with SessionLocal() as db:
        sermon = db.get(Sermon, sermon_id)
        sermon.status = SermonStatus.REVIEW_REQUIRED
        segment = sermon.segments[0]
        segment.translated_text = quote
        segment.citations = [citation(quote, quote)]
        segment_id = segment.id
        db.commit()
    headers = login_headers(client, "admin", "correct-horse-123")
    url = f"/api/v1/admin/sermons/{sermon_id}/segments/{segment_id}"
    blocked = client.patch(
        url, headers=headers, json={"translated_text": "Something else", "approved": True}
    )
    assert blocked.status_code == 409
    approved = client.patch(
        url, headers=headers, json={"translated_text": "Introduction: " + quote, "approved": True}
    )
    assert approved.status_code == 200
    assert approved.json()["citations"][0]["translation_start"] == 14
    preview = client.get(f"/api/v1/admin/sermons/{sermon_id}/preview", headers=headers)
    assert preview.status_code == 200
    assert "arabic_text" not in preview.json()["segments"][0]
    assert client.get(f"/api/v1/reader/sermons/{sermon_id}").status_code == 404
    assert client.get(f"/api/v1/admin/sermons/{sermon_id}/preview").status_code == 401


def test_restart_recovery_preserves_completed_sections(seeded_accounts):
    from test_workflow import _seed_sermon

    from app.db.session import SessionLocal
    from app.models import Sermon, SermonStatus
    from app.services.translation_recovery import recover_interrupted_translations

    sermon_id = _seed_sermon(seeded_accounts)
    with SessionLocal() as db:
        sermon = db.get(Sermon, sermon_id)
        sermon.status = SermonStatus.TRANSLATING
        sermon.segments[0].translated_text = "Saved section"
        db.commit()
    recover_interrupted_translations()
    with SessionLocal() as db:
        sermon = db.get(Sermon, sermon_id)
        assert sermon.status == SermonStatus.FAILED
        assert sermon.segments[0].translated_text == "Saved section"


def test_retry_translates_only_unfinished_sections(client, seeded_accounts, monkeypatch):
    from conftest import login_headers
    from test_workflow import _seed_sermon

    from app.db.session import SessionLocal
    from app.models import Sermon, SermonSegment, SermonStatus, VerificationStatus
    from app.services.providers.openai_provider import MockProvider

    translated = []

    class CountingProvider(MockProvider):
        async def translate(self, arabic_text, *args, **kwargs):
            translated.append(arabic_text)
            return await super().translate(arabic_text, *args, **kwargs)

    monkeypatch.setattr("app.services.translation.build_provider", CountingProvider)
    sermon_id = _seed_sermon(seeded_accounts)
    with SessionLocal() as db:
        sermon = db.get(Sermon, sermon_id)
        sermon.status = SermonStatus.FAILED
        sermon.segments[0].translated_text = "Saved, reviewed translation."
        sermon.segments[0].verification_status = VerificationStatus.HUMAN_APPROVED
        sermon.segments.append(SermonSegment(ordinal=1, arabic_text="والصلاة والسلام"))
        db.commit()
    headers = login_headers(client, "admin", "correct-horse-123")
    response = client.post(f"/api/v1/admin/sermons/{sermon_id}/translate", headers=headers)
    assert response.status_code == 200
    assert translated == ["والصلاة والسلام"]
    with SessionLocal() as db:
        sermon = db.get(Sermon, sermon_id)
        assert sermon.status == SermonStatus.REVIEW_REQUIRED
        assert sermon.segments[0].translated_text == "Saved, reviewed translation."
        assert sermon.segments[0].verification_status == VerificationStatus.HUMAN_APPROVED


def test_duplicate_start_does_not_enqueue_another_job(client, seeded_accounts, monkeypatch):
    from conftest import login_headers
    from test_workflow import _seed_sermon

    calls = []

    async def hold_job(sermon_id):
        calls.append(sermon_id)

    monkeypatch.setattr("app.api.routes.admin.run_translation_job", hold_job)
    sermon_id = _seed_sermon(seeded_accounts)
    headers = login_headers(client, "admin", "correct-horse-123")
    url = f"/api/v1/admin/sermons/{sermon_id}/translate"
    assert client.post(url, headers=headers).status_code == 200
    assert client.post(url, headers=headers).status_code == 409
    assert calls == [sermon_id]
