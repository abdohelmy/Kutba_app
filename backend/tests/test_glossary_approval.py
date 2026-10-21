from conftest import login_headers
from test_glossary_contributions import make_sermon

from app.db.session import SessionLocal
from app.models.entities import GlobalGlossaryTerm
from app.services.mosque_glossary import glossary_entries_for_mosque

PAYLOAD = {
    "arabic_term": "كلمةاختبار",
    "literal_translation": "test expression",
    "meaning": "A contextual test definition.",
}


def test_mosque_submission_needs_owner_approval_and_edits_reset_it(
    client, seeded_accounts, owner_headers
):
    headers = login_headers(client, "admin", "correct-horse-123")
    response = client.post("/api/v1/admin/glossary", headers=headers, json=PAYLOAD)
    assert response.status_code == 201
    term = response.json()
    assert term["approval_status"] == "PENDING"
    with SessionLocal() as db:
        assert not any(
            e.arabic_term == PAYLOAD["arabic_term"]
            for e in glossary_entries_for_mosque(db, seeded_accounts["mosque_id"])
        )
    path = f"/api/v1/owner/glossary/mosque/{term['id']}"
    assert client.patch(path, headers=headers, json={"action": "approve"}).status_code == 403
    assert client.patch(path, json={"action": "approve"}).status_code == 401
    assert client.patch(path, headers=owner_headers, json={"action": "approve"}).status_code == 200
    with SessionLocal() as db:
        assert any(
            e.meaning == PAYLOAD["meaning"]
            for e in glossary_entries_for_mosque(db, seeded_accounts["mosque_id"])
        )
        assert not any(
            e.meaning == PAYLOAD["meaning"]
            for e in glossary_entries_for_mosque(db, seeded_accounts["other_mosque_id"])
        )
    edit = {**PAYLOAD, "meaning": "An updated test definition."}
    response = client.put(f"/api/v1/admin/glossary/{term['id']}", headers=headers, json=edit)
    assert response.json()["approval_status"] == "PENDING"
    assert (
        client.get("/api/v1/owner/dashboard", headers=owner_headers).json()["pending_glossary"] == 1
    )
    client.patch(path, headers=owner_headers, json={"action": "reject"})
    assert (
        client.get("/api/v1/admin/glossary", headers=headers).json()[0]["approval_status"]
        == "REJECTED"
    )
    response = client.put(f"/api/v1/admin/glossary/{term['id']}", headers=headers, json=edit)
    assert response.json()["approval_status"] == "PENDING"


def test_rejected_global_contribution_can_be_corrected_and_resubmitted(
    client, seeded_accounts, owner_headers
):
    sermon_id, segment_id = make_sermon(seeded_accounts)
    headers = login_headers(client, "admin", "correct-horse-123")
    payload = {
        "segment_id": segment_id,
        "arabic_term": "كلمةغامضة",
        "literal_translation": "contextual insight",
        "meaning": "First explanation.",
    }
    base = f"/api/v1/admin/sermons/{sermon_id}"
    assert (
        client.post(base + "/glossary-contributions", headers=headers, json=payload).json()[
            "status"
        ]
        == "pending_approval"
    )
    terms = client.get("/api/v1/owner/glossary", headers=owner_headers).json()["global"]
    term = next(t for t in terms if t["arabic_term"] == "كلمةغامضة")
    assert term["submitted_by"] == "Central Mosque"
    client.patch(
        f"/api/v1/owner/glossary/global/{term['id']}",
        headers=owner_headers,
        json={"action": "reject"},
    )
    assert len(client.get(base + "/glossary-candidates", headers=headers).json()) == 1
    payload["meaning"] = "Corrected explanation."
    assert (
        client.post(base + "/glossary-contributions", headers=headers, json=payload).status_code
        == 201
    )
    with SessionLocal() as db:
        row = db.get(GlobalGlossaryTerm, term["id"])
        assert row.approval_status == "PENDING"
        assert row.meaning == "Corrected explanation."


def test_city_update_is_scoped_and_old_clients_can_still_rename(client, seeded_accounts):
    headers = login_headers(client, "admin", "correct-horse-123")
    result = client.patch(
        "/api/v1/admin/profile",
        headers=headers,
        json={"mosque_name": "Central Mosque", "city": "Odense"},
    )
    assert result.status_code == 200
    assert result.json()["city"] == "Odense"
    result = client.patch(
        "/api/v1/admin/profile", headers=headers, json={"mosque_name": "Renamed Mosque"}
    )
    assert result.json()["city"] == "Odense"
    assert (
        client.patch(
            "/api/v1/admin/profile",
            headers=headers,
            json={"mosque_name": "Renamed Mosque", "city": " "},
        ).status_code
        == 422
    )
    names = client.get("/api/v1/reader/mosques").json()
    assert (
        next(m for m in names if m["id"] == seeded_accounts["other_mosque_id"])["city"] == "Aarhus"
    )
