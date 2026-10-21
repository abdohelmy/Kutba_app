import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from conftest import login_headers
from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import Mosque, User, UserRole
from app.models.entities import PasswordReset


@pytest.fixture
def owner_headers(client):
    with SessionLocal() as db:
        user = User(
            username="owner",
            display_name="Owner",
            role=UserRole.SUPER_ADMIN,
            contact_email="owner@example.com",
            password_hash=hash_password("owner123"),
        )
        db.add(user)
        db.commit()
    return login_headers(client, "owner", "owner123")


def register(client):
    response = client.post(
        "/api/v1/auth/register-mosque",
        json={
            "mosque_name": "New Mosque",
            "city": "Odense",
            "country": "DK",
            "admin_display_name": "Admin",
            "username": "newmosque",
            "password": "mosque123",
            "contact_email": "admin@example.com",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_registration_approval_and_session_revocation(client, owner_headers):
    account = register(client)
    mosque_id = account["mosque_id"]
    assert client.get("/api/v1/reader/mosques").json() == []
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"username": "newmosque", "password": "mosque123", "account_type": "MOSQUE"},
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/v1/owner/mosques/{mosque_id}", headers=owner_headers, json={"action": "approve"}
        ).status_code
        == 200
    )
    headers = login_headers(client, "newmosque", "mosque123")
    assert client.get("/api/v1/admin/profile", headers=headers).status_code == 200
    assert len(client.get("/api/v1/reader/mosques").json()) == 1
    assert (
        client.patch(
            f"/api/v1/owner/mosques/{mosque_id}", headers=owner_headers, json={"action": "suspend"}
        ).status_code
        == 200
    )
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    assert client.get("/api/v1/reader/mosques").json() == []
    client.patch(
        f"/api/v1/owner/mosques/{mosque_id}", headers=owner_headers, json={"action": "restore"}
    )
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    assert login_headers(client, "newmosque", "mosque123")


def test_mosque_and_reader_cannot_access_owner_operations(client, seeded_accounts):
    for headers in [
        None,
        login_headers(client, "admin", "correct-horse-123"),
        login_headers(client, "reader", "reader-password-123", "INDIVIDUAL"),
    ]:
        assert client.get("/api/v1/owner/dashboard", headers=headers).status_code in {401, 403}
        assert client.patch(
            f"/api/v1/owner/mosques/{seeded_accounts['mosque_id']}",
            headers=headers,
            json={"action": "approve"},
        ).status_code in {401, 403}
        assert client.put(
            "/api/v1/owner/glossary",
            headers=headers,
            json={
                "arabic_term": "test",
                "meaning": "Test definition",
                "literal_translation": "test",
            },
        ).status_code in {401, 403}


def test_owner_rename_reject_and_archive(client, owner_headers):
    account = register(client)
    path = f"/api/v1/owner/mosques/{account['mosque_id']}"
    assert (
        client.patch(
            path, headers=owner_headers, json={"name": "Renamed Mosque", "action": "reject"}
        ).status_code
        == 200
    )
    assert client.patch(path, headers=owner_headers, json={"action": "restore"}).status_code == 409
    assert client.delete(path, headers=owner_headers).status_code == 204
    with SessionLocal() as db:
        assert db.get(Mosque, account["mosque_id"]).approval_status == "REMOVED"
        assert not db.get(User, account["id"]).is_active
    assert len(client.get("/api/v1/owner/audit", headers=owner_headers).json()) == 2


def test_single_use_password_reset_revokes_sessions(client, owner_headers, seeded_accounts):
    old_headers = login_headers(client, "admin", "correct-horse-123")
    response = client.post(
        f"/api/v1/owner/users/{seeded_accounts['admin_id']}/reset-link", headers=owner_headers
    )
    assert response.status_code == 200
    token = response.json()["link"].split("#reset/")[1]
    with SessionLocal() as db:
        reset = db.scalar(select(PasswordReset))
        assert reset.token_hash == hashlib.sha256(token.encode()).hexdigest()
        assert reset.token_hash != token
    payload = {"token": token, "password": "newpass123"}
    assert client.post("/api/v1/auth/reset-password", json=payload).status_code == 200
    assert client.post("/api/v1/auth/reset-password", json=payload).status_code == 400
    assert client.get("/api/v1/auth/me", headers=old_headers).status_code == 401
    assert login_headers(client, "admin", "newpass123")


def test_expired_and_superseded_links_fail(client, owner_headers, seeded_accounts):
    path = f"/api/v1/owner/users/{seeded_accounts['admin_id']}/reset-link"
    token = client.post(path, headers=owner_headers).json()["link"].split("#reset/")[1]
    newer = client.post(path, headers=owner_headers).json()["link"].split("#reset/")[1]
    assert (
        client.post(
            "/api/v1/auth/reset-password", json={"token": token, "password": "newpass"}
        ).status_code
        == 400
    )
    with SessionLocal() as db:
        reset = db.scalar(
            select(PasswordReset).where(
                PasswordReset.token_hash == hashlib.sha256(newer.encode()).hexdigest()
            )
        )
        reset.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
        db.commit()
    assert (
        client.post(
            "/api/v1/auth/reset-password", json={"token": newer, "password": "newpass"}
        ).status_code
        == 400
    )


def test_owner_glossary_override_is_used_and_removal_restores_base(
    client, owner_headers, seeded_accounts
):
    from app.services.mosque_glossary import glossary_entries_for_mosque

    payload = {
        "arabic_term": "التقوى",
        "literal_translation": "God-consciousness",
        "meaning": "Owner supplied definition",
    }
    assert (
        client.put("/api/v1/owner/glossary", headers=owner_headers, json=payload).status_code == 200
    )
    with SessionLocal() as db:
        terms = glossary_entries_for_mosque(db, seeded_accounts["mosque_id"])
        assert any(t.meaning == payload["meaning"] for t in terms)
    items = client.get("/api/v1/owner/glossary", headers=owner_headers).json()["global"]
    term = next(t for t in items if t["meaning"] == payload["meaning"])
    assert (
        client.delete(
            f"/api/v1/owner/glossary/global/{term['id']}", headers=owner_headers
        ).status_code
        == 204
    )


def test_account_disable_and_reenable_revokes_token(client, owner_headers, seeded_accounts):
    headers = login_headers(client, "admin", "correct-horse-123")
    path = f"/api/v1/owner/users/{seeded_accounts['admin_id']}"
    assert client.patch(path, headers=owner_headers, json={"is_active": False}).status_code == 200
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    assert (
        client.patch(
            path,
            headers=owner_headers,
            json={"is_active": True, "contact_email": "new@example.com"},
        ).status_code
        == 200
    )
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    assert login_headers(client, "admin", "correct-horse-123")


def test_no_email_service_has_clear_recovery_error(client):
    response = client.post("/api/v1/auth/forgot-password", json={"username": "owner"})
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]


def test_migration_preserves_existing_accounts_and_is_idempotent(tmp_path):
    from sqlalchemy import create_engine, text

    from app.db.migrations import migrate_super_admin

    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as db:
        db.execute(text("CREATE TABLE mosques(id TEXT PRIMARY KEY, name TEXT, is_active BOOLEAN)"))
        db.execute(text("CREATE TABLE users(id TEXT PRIMARY KEY, email TEXT, password_hash TEXT)"))
        db.execute(text("INSERT INTO mosques VALUES ('m', 'Existing mosque', 1)"))
        db.execute(text("INSERT INTO users VALUES ('u', 'existing', 'unchanged')"))
    migrate_super_admin(engine)
    migrate_super_admin(engine)
    with engine.connect() as db:
        assert db.execute(text("SELECT name, is_active, approval_status FROM mosques")).one() == (
            "Existing mosque",
            1,
            "APPROVED",
        )
        assert db.execute(
            text("SELECT email, password_hash, auth_version, contact_email FROM users")
        ).one() == ("existing", "unchanged", 0, None)


def test_suspended_mosque_blocks_direct_reader_links(client, owner_headers, seeded_accounts):
    from datetime import date

    from app.models import Sermon, SermonStatus

    with SessionLocal() as db:
        sermon = Sermon(
            mosque_id=seeded_accounts["mosque_id"],
            title="Public khutba",
            khutba_date=date(2026, 10, 2),
            target_language="en",
            source_file_path="test.pdf",
            source_file_sha256="a" * 64,
            arabic_text="اختبار",
            created_by=seeded_accounts["admin_id"],
            status=SermonStatus.PUBLISHED,
        )
        db.add(sermon)
        db.commit()
        sermon_id = sermon.id
    client.patch(
        f"/api/v1/owner/mosques/{seeded_accounts['mosque_id']}",
        headers=owner_headers,
        json={"action": "suspend"},
    )
    assert (
        client.get(f"/api/v1/reader/mosques/{seeded_accounts['mosque_id']}/sermons").status_code
        == 404
    )
    assert client.get(f"/api/v1/reader/sermons/{sermon_id}").status_code == 404
    assert client.get(f"/api/v1/reader/sermons/{sermon_id}/pdf").status_code == 404


def test_owner_sermon_write_is_audited(client, owner_headers, seeded_accounts):
    from datetime import date

    from app.models import Sermon

    with SessionLocal() as db:
        sermon = Sermon(
            mosque_id=seeded_accounts["mosque_id"],
            title="Original",
            khutba_date=date(2026, 10, 2),
            target_language="en",
            source_file_path="test.pdf",
            source_file_sha256="a" * 64,
            arabic_text="اختبار",
            created_by=seeded_accounts["admin_id"],
        )
        db.add(sermon)
        db.commit()
        sermon_id = sermon.id
    assert (
        client.patch(
            f"/api/v1/admin/sermons/{sermon_id}/title",
            headers=owner_headers,
            json={"title": "Updated"},
        ).status_code
        == 200
    )
    audit = client.get("/api/v1/owner/audit", headers=owner_headers).json()
    assert any(row["action"] == "PATCH" and sermon_id in row["target_id"] for row in audit)
