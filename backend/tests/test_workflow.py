from datetime import date

from app.db.session import SessionLocal
from app.models import Sermon, SermonSegment, SermonStatus, SourceChunk, TrustedSource
from app.services.canonical_sources import CanonicalRetrieval
from app.services.retrieval import RetrievedSource


def _seed_sermon_and_source(account_ids: dict[str, str]) -> str:
    with SessionLocal() as db:
        source = TrustedSource(
            mosque_id=account_ids["mosque_id"],
            title="Approved Qur'an Translation",
            authority="Mosque Translation Committee",
            language="en",
            file_path="tests/source.pdf",
            sha256="a" * 64,
        )
        db.add(source)
        db.flush()
        db.add(
            SourceChunk(
                source_id=source.id,
                ordinal=0,
                text="All praise is due to Allah, Lord of all worlds.",
            )
        )
        sermon = Sermon(
            mosque_id=account_ids["mosque_id"],
            title="Patience and Gratitude",
            khutba_date=date(2026, 7, 31),
            target_language="en",
            source_file_path="tests/sermon.pdf",
            source_file_sha256="b" * 64,
            arabic_text="الحمد لله رب العالمين",
            status=SermonStatus.DRAFT,
            created_by=account_ids["admin_id"],
        )
        sermon.segments = [SermonSegment(ordinal=0, arabic_text=sermon.arabic_text)]
        db.add(sermon)
        db.commit()
        return sermon.id


def test_translation_requires_review_before_publication(client, seeded_accounts):
    from conftest import login_headers

    sermon_id = _seed_sermon_and_source(seeded_accounts)
    admin_headers = login_headers(client, "admin@example.com", "correct-horse-123")
    reader_headers = login_headers(client, "reader@example.com", "reader-password-123")

    queued = client.post(f"/api/v1/admin/sermons/{sermon_id}/translate", headers=admin_headers)
    assert queued.status_code == 200
    assert queued.json()["status"] == SermonStatus.TRANSLATING

    detail = client.get(f"/api/v1/admin/sermons/{sermon_id}", headers=admin_headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == SermonStatus.REVIEW_REQUIRED
    assert body["segments"][0]["translated_text"].startswith("[en]")
    assert body["segments"][0]["citations"][0]["title"] == "Approved Qur'an Translation"

    blocked = client.post(f"/api/v1/admin/sermons/{sermon_id}/publish", headers=admin_headers)
    assert blocked.status_code == 409
    assert (
        client.get(f"/api/v1/reader/sermons/{sermon_id}", headers=reader_headers).status_code == 404
    )

    segment_id = body["segments"][0]["id"]
    approved = client.patch(
        f"/api/v1/admin/sermons/{sermon_id}/segments/{segment_id}",
        headers=admin_headers,
        json={
            "translated_text": "All praise is due to Allah, Lord of all worlds.",
            "approved": True,
            "reviewer_note": "Checked against the committee-approved wording.",
        },
    )
    assert approved.status_code == 200
    assert approved.json()["verification_status"] == "HUMAN_APPROVED"

    published = client.post(f"/api/v1/admin/sermons/{sermon_id}/publish", headers=admin_headers)
    assert published.status_code == 200
    public = client.get(f"/api/v1/reader/sermons/{sermon_id}", headers=reader_headers)
    assert public.status_code == 200
    assert public.json()["segments"][0]["translated_text"].startswith("All praise")


def test_canonical_source_link_is_persisted_for_review(client, seeded_accounts, monkeypatch):
    from conftest import login_headers

    async def canonical_retrieve(_service, _arabic_text):
        return CanonicalRetrieval(
            sources=[
                RetrievedSource(
                    chunk_id="canonical:quran:1:2",
                    source_id="quran.com:1:2",
                    title="Qur'an 1:2 — Saheeh International",
                    authority="Quran.com",
                    text="[All] praise is [due] to Allah, Lord of the worlds.",
                    score=10_000,
                    source_kind="quran",
                    url="https://quran.com/1/2",
                    canonical=True,
                )
            ],
            issues=[],
        )

    monkeypatch.setattr(
        "app.services.translation.CanonicalSourceService.retrieve", canonical_retrieve
    )
    sermon_id = _seed_sermon_and_source(seeded_accounts)
    headers = login_headers(client, "admin@example.com", "correct-horse-123")

    queued = client.post(f"/api/v1/admin/sermons/{sermon_id}/translate", headers=headers)
    assert queued.status_code == 200
    detail = client.get(f"/api/v1/admin/sermons/{sermon_id}", headers=headers).json()

    citation = detail["segments"][0]["citations"][0]
    assert citation["source_kind"] == "quran"
    assert citation["url"] == "https://quran.com/1/2"


def test_mosque_admin_is_tenant_scoped(client, seeded_accounts):
    from conftest import login_headers

    with SessionLocal() as db:
        sermon = Sermon(
            mosque_id=seeded_accounts["other_mosque_id"],
            title="Other Mosque Sermon",
            khutba_date=date(2026, 7, 31),
            target_language="en",
            source_file_path="tests/other.pdf",
            source_file_sha256="c" * 64,
            arabic_text="الحمد لله رب العالمين",
            status=SermonStatus.DRAFT,
            created_by=seeded_accounts["admin_id"],
        )
        sermon.segments = [SermonSegment(ordinal=0, arabic_text=sermon.arabic_text)]
        db.add(sermon)
        db.commit()
        sermon_id = sermon.id

    headers = login_headers(client, "admin@example.com", "correct-horse-123")
    response = client.get(f"/api/v1/admin/sermons/{sermon_id}", headers=headers)
    assert response.status_code == 403
