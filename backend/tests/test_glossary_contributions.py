from datetime import UTC, date, datetime

from conftest import login_headers

from app.db.session import SessionLocal
from app.models import Sermon, SermonSegment, SermonStatus
from app.services.mosque_glossary import glossary_entries_for_mosque


def make_sermon(accounts, *, mosque_id=None, status=SermonStatus.PUBLISHED):
    with SessionLocal() as db:
        sermon = Sermon(
            mosque_id=mosque_id or accounts["mosque_id"],
            title="Test",
            khutba_date=date.today(),
            target_language="en",
            source_file_path="test.pdf",
            source_file_sha256="0" * 64,
            arabic_text="كلمةغامضة",
            status=status,
            created_by=accounts["admin_id"],
            published_at=datetime.now(UTC),
        )
        sermon.segments = [
            SermonSegment(
                ordinal=0,
                arabic_text="كلمةغامضة التقوى",
                translated_text="Develop contextual insight (كلمةغامضة). Cultivate piety (التقوى).",
            )
        ]
        db.add(sermon)
        db.commit()
        return sermon.id, sermon.segments[0].id


def test_post_publish_definition_is_shared_after_approval_without_retranslation(
    client, seeded_accounts, owner_headers
):
    sermon_id, segment_id = make_sermon(seeded_accounts)
    headers = login_headers(client, "admin", "correct-horse-123")
    base = f"/api/v1/admin/sermons/{sermon_id}"
    candidates = client.get(base + "/glossary-candidates", headers=headers)
    assert candidates.status_code == 200
    assert [c["arabic_term"] for c in candidates.json()] == ["كلمةغامضة"]
    payload = dict(
        segment_id=segment_id,
        arabic_term="كلمةغامضة",
        literal_translation="contextual insight",
        meaning="Understanding the context.",
    )
    assert (
        client.post(base + "/glossary-contributions", headers=headers, json=payload).status_code
        == 201
    )
    assert client.get(base + "/glossary-candidates", headers=headers).json() == []
    assert (
        client.post(base + "/glossary-contributions", headers=headers, json=payload).status_code
        == 409
    )
    with SessionLocal() as db:
        assert not any(
            e.arabic_term == "كلمةغامضة"
            for e in glossary_entries_for_mosque(db, seeded_accounts["other_mosque_id"])
        )
    terms = client.get("/api/v1/owner/glossary", headers=owner_headers).json()["global"]
    term = next(t for t in terms if t["arabic_term"] == "كلمةغامضة")
    assert term["approval_status"] == "PENDING"
    assert (
        client.patch(
            f"/api/v1/owner/glossary/global/{term['id']}",
            headers=owner_headers,
            json={"action": "approve"},
        ).status_code
        == 200
    )
    with SessionLocal() as db:
        assert any(
            e.arabic_term == "كلمةغامضة"
            for e in glossary_entries_for_mosque(db, seeded_accounts["other_mosque_id"])
        )
    detail = client.get(f"/api/v1/reader/sermons/{sermon_id}")
    assert detail.status_code == 200
    terms = detail.json()["segments"][0]["glossary_terms"]
    assert any(
        t["display_term"] == "كلمةغامضة"
        and t["english_phrase"] == "contextual insight"
        and t["meaning"] == payload["meaning"]
        for t in terms
    )


def test_candidates_require_published_owned_sermon(client, seeded_accounts):
    headers = login_headers(client, "admin", "correct-horse-123")
    other, _ = make_sermon(seeded_accounts, mosque_id=seeded_accounts["other_mosque_id"])
    draft, _ = make_sermon(seeded_accounts, status=SermonStatus.DRAFT)
    assert (
        client.get(
            f"/api/v1/admin/sermons/{other}/glossary-candidates", headers=headers
        ).status_code
        == 403
    )
    assert (
        client.get(
            f"/api/v1/admin/sermons/{draft}/glossary-candidates", headers=headers
        ).status_code
        == 409
    )


def test_rejects_wrong_phrase_empty_meaning_and_unrelated_term(client, seeded_accounts):
    sermon_id, segment_id = make_sermon(seeded_accounts)
    headers = login_headers(client, "admin", "correct-horse-123")
    url = f"/api/v1/admin/sermons/{sermon_id}/glossary-contributions"
    payload = dict(
        segment_id=segment_id,
        arabic_term="كلمةغامضة",
        literal_translation="not in the sermon",
        meaning="A meaning.",
    )
    assert client.post(url, headers=headers, json=payload).status_code == 422
    payload.update(literal_translation="contextual insight", meaning="   ")
    assert client.post(url, headers=headers, json=payload).status_code == 422
    payload.update(meaning="A meaning.", arabic_term="التقوى")
    assert client.post(url, headers=headers, json=payload).status_code == 409


def test_quotes_and_hallucinated_terms_are_not_candidates(client, seeded_accounts):
    sermon_id, segment_id = make_sermon(seeded_accounts)
    with SessionLocal() as db:
        segment = db.get(SermonSegment, segment_id)
        segment.translated_text = "“Insight (كلمةغامضة).” Another (كلمةمختلقة)."
        db.commit()
    headers = login_headers(client, "admin", "correct-horse-123")
    response = client.get(f"/api/v1/admin/sermons/{sermon_id}/glossary-candidates", headers=headers)
    assert response.status_code == 200
    assert response.json() == []


def test_known_component_does_not_hide_missing_expression(client, seeded_accounts):
    sermon_id, segment_id = make_sermon(seeded_accounts)
    with SessionLocal() as db:
        segment = db.get(SermonSegment, segment_id)
        segment.arabic_text = "التقوى كلمةغامضة"
        segment.translated_text = "A contextual expression (التقوى كلمةغامضة)."
        db.commit()
    headers = login_headers(client, "admin", "correct-horse-123")
    response = client.get(f"/api/v1/admin/sermons/{sermon_id}/glossary-candidates", headers=headers)
    assert response.status_code == 200
    assert response.json()[0]["arabic_term"] == "التقوى كلمةغامضة"
