from datetime import date

from app.db.session import SessionLocal
from app.models import Sermon, SermonSegment, SermonStatus, VerificationStatus
from app.services.canonical_sources import CanonicalRetrieval
from app.services.retrieval import RetrievedSource


def _seed_sermon(account_ids: dict[str, str]) -> str:
    with SessionLocal() as db:
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

    sermon_id = _seed_sermon(seeded_accounts)
    admin_headers = login_headers(client, "admin", "correct-horse-123")

    queued = client.post(f"/api/v1/admin/sermons/{sermon_id}/translate", headers=admin_headers)
    assert queued.status_code == 200
    assert queued.json()["status"] == SermonStatus.TRANSLATING

    detail = client.get(f"/api/v1/admin/sermons/{sermon_id}", headers=admin_headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == SermonStatus.REVIEW_REQUIRED
    assert body["segments"][0]["translated_text"].startswith("[en]")
    assert body["segments"][0]["citations"] == []

    blocked = client.post(f"/api/v1/admin/sermons/{sermon_id}/publish", headers=admin_headers)
    assert blocked.status_code == 409
    assert client.get(f"/api/v1/reader/sermons/{sermon_id}").status_code == 404
    assert client.get(f"/api/v1/reader/sermons/{sermon_id}/pdf").status_code == 404

    segment_id = body["segments"][0]["id"]
    approved = client.patch(
        f"/api/v1/admin/sermons/{sermon_id}/segments/{segment_id}",
        headers=admin_headers,
        json={
            "translated_text": "All praise is due to Allah, Lord of all worlds.",
            "approved": True,
            "reviewer_note": "Checked directly against the Arabic source.",
        },
    )
    assert approved.status_code == 200
    assert approved.json()["verification_status"] == "HUMAN_APPROVED"

    published = client.post(f"/api/v1/admin/sermons/{sermon_id}/publish", headers=admin_headers)
    assert published.status_code == 200
    public = client.get(f"/api/v1/reader/sermons/{sermon_id}")
    assert public.status_code == 200
    public_segment = public.json()["segments"][0]
    assert public_segment["translated_text"].startswith("All praise")
    assert "arabic_text" not in public_segment
    assert "issues" not in public_segment
    assert "reviewer_note" not in public_segment

    pdf = client.get(f"/api/v1/reader/sermons/{sermon_id}/pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.headers["content-disposition"].startswith("attachment;")
    assert pdf.content.startswith(b"%PDF-")


def test_translation_can_start_without_canonical_reference(client, seeded_accounts):
    from conftest import login_headers

    with SessionLocal() as db:
        sermon = Sermon(
            mosque_id=seeded_accounts["mosque_id"],
            title="Unreferenced prose",
            khutba_date=date(2026, 8, 1),
            target_language="en",
            source_file_path="tests/sermon.pdf",
            source_file_sha256="d" * 64,
            arabic_text="الحمد لله رب العالمين",
            status=SermonStatus.DRAFT,
            created_by=seeded_accounts["admin_id"],
        )
        sermon.segments = [SermonSegment(ordinal=0, arabic_text=sermon.arabic_text)]
        db.add(sermon)
        db.commit()
        sermon_id = sermon.id

    headers = login_headers(client, "admin", "correct-horse-123")
    queued = client.post(f"/api/v1/admin/sermons/{sermon_id}/translate", headers=headers)
    assert queued.status_code == 200
    detail = client.get(f"/api/v1/admin/sermons/{sermon_id}", headers=headers).json()
    assert detail["status"] == SermonStatus.REVIEW_REQUIRED
    assert detail["segments"][0]["citations"] == []
    assert (
        "review the translation directly against the Arabic" in detail["segments"][0]["issues"][0]
    )


def test_canonical_source_link_is_persisted_for_review(client, seeded_accounts, monkeypatch):
    from conftest import login_headers

    async def canonical_retrieve_quran(_service, _arabic_text):
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
                    arabic_text="الْحَمْدُ لِلَّهِ رَبِّ الْعَالَمِينَ",
                    transliteration="Al-hamdu lillahi rabbi al-alamin",
                    display_reference="Al-Fatihah 1:2",
                )
            ],
            issues=[],
        )

    async def canonical_retrieve_hadith(_service, _arabic_text):
        return CanonicalRetrieval(sources=[], issues=[])

    monkeypatch.setattr(
        "app.services.translation.CanonicalSourceService.retrieve_quran",
        canonical_retrieve_quran,
    )
    monkeypatch.setattr(
        "app.services.translation.CanonicalSourceService.retrieve_hadith",
        canonical_retrieve_hadith,
    )
    sermon_id = _seed_sermon(seeded_accounts)
    headers = login_headers(client, "admin", "correct-horse-123")

    queued = client.post(f"/api/v1/admin/sermons/{sermon_id}/translate", headers=headers)
    assert queued.status_code == 200
    detail = client.get(f"/api/v1/admin/sermons/{sermon_id}", headers=headers).json()

    citation = detail["segments"][0]["citations"][0]
    assert citation["source_kind"] == "quran"
    assert citation["url"] == "https://quran.com/1/2"
    assert citation["arabic_excerpt"] == "الْحَمْدُ لِلَّهِ رَبِّ الْعَالَمِينَ"
    assert citation["transliteration"] == "Al-hamdu lillahi rabbi al-alamin"
    assert citation["display_reference"] == "Al-Fatihah 1:2"


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

    headers = login_headers(client, "admin", "correct-horse-123")
    response = client.get(f"/api/v1/admin/sermons/{sermon_id}", headers=headers)
    assert response.status_code == 403


def test_reader_routes_are_public(client, seeded_accounts):
    mosques = client.get("/api/v1/reader/mosques")
    assert mosques.status_code == 200
    assert {item["id"] for item in mosques.json()} == {
        seeded_accounts["mosque_id"],
        seeded_accounts["other_mosque_id"],
    }

    sermons = client.get(f"/api/v1/reader/mosques/{seeded_accounts['mosque_id']}/sermons")
    assert sermons.status_code == 200


def test_glossary_term_is_returned_only_for_its_first_sermon_occurrence(client, seeded_accounts):
    with SessionLocal() as db:
        sermon = Sermon(
            mosque_id=seeded_accounts["mosque_id"],
            title="Taqwa",
            khutba_date=date(2026, 8, 7),
            target_language="en",
            source_file_path="tests/sermon.pdf",
            source_file_sha256="e" * 64,
            arabic_text="التقوى تحفظ المؤمن. ومن ثمرات التقوى الاستقامة.",
            status=SermonStatus.PUBLISHED,
            created_by=seeded_accounts["admin_id"],
        )
        sermon.segments = [
            SermonSegment(
                ordinal=0,
                arabic_text="التقوى تحفظ المؤمن.",
                translated_text="God-consciousness (التقوى) protects the believer.",
                verification_status=VerificationStatus.HUMAN_APPROVED,
            ),
            SermonSegment(
                ordinal=1,
                arabic_text="ومن ثمرات التقوى الاستقامة.",
                translated_text="Another fruit of God-consciousness (التقوى) is uprightness.",
                verification_status=VerificationStatus.HUMAN_APPROVED,
            ),
        ]
        db.add(sermon)
        db.commit()
        sermon_id = sermon.id

    response = client.get(f"/api/v1/reader/sermons/{sermon_id}")
    assert response.status_code == 200
    segments = response.json()["segments"]
    assert len(segments[0]["glossary_terms"]) == 1
    term = segments[0]["glossary_terms"][0]
    assert term["arabic_term"] == "التقوى"
    assert term["display_term"] == "God-consciousness"
    assert "awareness of Allah" in term["meaning"]
    assert segments[1]["glossary_terms"] == []


def test_mosque_can_manage_a_term_that_overrides_the_builtin_glossary(client, seeded_accounts):
    from conftest import login_headers

    headers = login_headers(client, "admin", "correct-horse-123")
    created = client.post(
        "/api/v1/admin/glossary",
        headers=headers,
        json={
            "arabic_term": "العلم",
            "meaning": "Beneficial knowledge grounded in revelation and sound evidence.",
            "literal_translation": "sacred learning",
            "alternative_context_meanings": "With different vocalization it can mean a flag.",
        },
    )
    assert created.status_code == 201, created.text
    term_id = created.json()["id"]
    assert client.get("/api/v1/admin/glossary", headers=headers).json()[0]["id"] == term_id

    duplicate = client.post(
        "/api/v1/admin/glossary",
        headers=headers,
        json={
            "arabic_term": "الْعِلْم",
            "meaning": "A duplicate spelling with marks.",
            "literal_translation": "knowledge",
        },
    )
    assert duplicate.status_code == 409

    with SessionLocal() as db:
        sermon = Sermon(
            mosque_id=seeded_accounts["mosque_id"],
            title="Knowledge",
            khutba_date=date(2026, 8, 14),
            target_language="en",
            source_file_path="tests/knowledge.pdf",
            source_file_sha256="a" * 64,
            arabic_text="العلم النافع نور",
            status=SermonStatus.PUBLISHED,
            created_by=seeded_accounts["admin_id"],
        )
        sermon.segments = [
            SermonSegment(
                ordinal=0,
                arabic_text="العلم النافع نور",
                translated_text="Sacred learning (العلم) is a light.",
                verification_status=VerificationStatus.HUMAN_APPROVED,
            )
        ]
        db.add(sermon)
        db.commit()
        sermon_id = sermon.id

    public = client.get(f"/api/v1/reader/sermons/{sermon_id}")
    assert public.status_code == 200
    glossary = public.json()["segments"][0]["glossary_terms"]
    assert len(glossary) == 1
    assert glossary[0]["meaning"].startswith("Beneficial knowledge")
    assert glossary[0]["display_term"] == "Sacred learning"

    updated = client.put(
        f"/api/v1/admin/glossary/{term_id}",
        headers=headers,
        json={
            "arabic_term": "العلم",
            "meaning": "Reviewed explanation for beneficial knowledge.",
            "literal_translation": "sacred learning",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["meaning"].startswith("Reviewed explanation")

    deleted = client.delete(f"/api/v1/admin/glossary/{term_id}", headers=headers)
    assert deleted.status_code == 204
    assert client.get("/api/v1/admin/glossary", headers=headers).json() == []


def test_admin_can_delete_own_sermon_but_not_another_mosques_sermon(client, seeded_accounts):
    from conftest import login_headers

    own_sermon_id = _seed_sermon(seeded_accounts)
    headers = login_headers(client, "admin", "correct-horse-123")
    deleted = client.delete(f"/api/v1/admin/sermons/{own_sermon_id}", headers=headers)
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/admin/sermons/{own_sermon_id}", headers=headers).status_code == 404

    with SessionLocal() as db:
        other_sermon = Sermon(
            mosque_id=seeded_accounts["other_mosque_id"],
            title="Other mosque",
            khutba_date=date(2026, 8, 7),
            target_language="en",
            source_file_path="tests/other.pdf",
            source_file_sha256="f" * 64,
            arabic_text="الحمد لله رب العالمين",
            status=SermonStatus.DRAFT,
            created_by=seeded_accounts["admin_id"],
        )
        db.add(other_sermon)
        db.commit()
        other_sermon_id = other_sermon.id

    forbidden = client.delete(f"/api/v1/admin/sermons/{other_sermon_id}", headers=headers)
    assert forbidden.status_code == 403


def test_admin_can_hide_and_show_a_published_sermon(client, seeded_accounts):
    from conftest import login_headers

    with SessionLocal() as db:
        sermon = Sermon(
            mosque_id=seeded_accounts["mosque_id"],
            title="Patience",
            khutba_date=date(2026, 8, 14),
            target_language="en",
            source_file_path="tests/sermon.pdf",
            source_file_sha256="g" * 64,
            arabic_text="الحمد لله رب العالمين",
            status=SermonStatus.PUBLISHED,
            created_by=seeded_accounts["admin_id"],
        )
        sermon.segments = [
            SermonSegment(
                ordinal=0,
                arabic_text=sermon.arabic_text,
                translated_text="All praise is due to Allah, Lord of all worlds.",
                verification_status=VerificationStatus.HUMAN_APPROVED,
            )
        ]
        db.add(sermon)
        db.commit()
        sermon_id = sermon.id

    headers = login_headers(client, "admin", "correct-horse-123")
    hidden = client.post(f"/api/v1/admin/sermons/{sermon_id}/hide", headers=headers)
    assert hidden.status_code == 200
    assert hidden.json()["status"] == SermonStatus.HIDDEN
    public_list = client.get(
        f"/api/v1/reader/mosques/{seeded_accounts['mosque_id']}/sermons"
    )
    assert sermon_id not in {item["id"] for item in public_list.json()}
    assert client.get(f"/api/v1/reader/sermons/{sermon_id}").status_code == 404
    assert client.get(f"/api/v1/reader/sermons/{sermon_id}/pdf").status_code == 404

    shown = client.post(f"/api/v1/admin/sermons/{sermon_id}/show", headers=headers)
    assert shown.status_code == 200
    assert shown.json()["status"] == SermonStatus.PUBLISHED
    assert client.get(f"/api/v1/reader/sermons/{sermon_id}").status_code == 200
