from app.models import UserRole


def test_reader_can_register_login_and_access_mosques(client):
    register = client.post(
        "/api/v1/auth/register",
        json={
            "username": "new.reader",
            "display_name": "New Reader",
            "password": "reader12",
        },
    )
    assert register.status_code == 201
    assert register.json()["role"] == UserRole.READER

    login = client.post(
        "/api/v1/auth/login",
        json={
            "username": "new.reader",
            "password": "reader12",
            "account_type": "INDIVIDUAL",
        },
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/api/v1/reader/mosques", headers=headers).status_code == 200


def test_published_reader_routes_allow_guest_access(client):
    response = client.get("/api/v1/reader/mosques")
    assert response.status_code == 200


def test_mosque_registration_requires_permission_password(client):
    payload = {
        "mosque_name": "New Community Mosque",
        "city": "Odense",
        "country": "dk",
        "admin_display_name": "Mosque Administrator",
        "username": "newmosque",
        "password": "mosque12",
        "permission_password": "wrong-password",
    }
    rejected = client.post("/api/v1/auth/register-mosque", json=payload)
    assert rejected.status_code == 403
    assert rejected.json()["detail"] == "Invalid mosque permission password"
    assert client.get("/api/v1/reader/mosques").json() == []


def test_mosque_can_register_with_permission_password_and_login(client):
    register = client.post(
        "/api/v1/auth/register-mosque",
        json={
            "mosque_name": "New Community Mosque",
            "city": "Odense",
            "country": "dk",
            "admin_display_name": "Mosque Administrator",
            "username": "newmosque",
            "password": "mosque12",
            "permission_password": "01082025",
        },
    )
    assert register.status_code == 201
    created = register.json()
    assert created["role"] == UserRole.MOSQUE_ADMIN
    assert created["mosque_id"]

    login = client.post(
        "/api/v1/auth/login",
        json={
            "username": "newmosque",
            "password": "mosque12",
            "account_type": "MOSQUE",
        },
    )
    assert login.status_code == 200
    mosques = client.get("/api/v1/reader/mosques").json()
    assert mosques == [
        {
            "id": created["mosque_id"],
            "name": "New Community Mosque",
            "city": "Odense",
            "country": "DK",
        }
    ]


def test_username_can_exist_once_per_login_type_and_password_minimum_is_six(
    client, seeded_accounts
):
    accepted = client.post(
        "/api/v1/auth/register",
        json={"username": "admin", "display_name": "Reader Admin", "password": "sixsix"},
    )
    assert accepted.status_code == 201

    reader_login = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "sixsix", "account_type": "INDIVIDUAL"},
    )
    assert reader_login.status_code == 200
    mosque_login = client.post(
        "/api/v1/auth/login",
        json={
            "username": "admin",
            "password": "correct-horse-123",
            "account_type": "MOSQUE",
        },
    )
    assert mosque_login.status_code == 200

    rejected = client.post(
        "/api/v1/auth/register",
        json={"username": "shortpass", "display_name": "Short", "password": "12345"},
    )
    assert rejected.status_code == 422


def test_reader_cannot_access_admin_routes(client, seeded_accounts):
    from conftest import login_headers

    headers = login_headers(client, "reader", "reader-password-123", "INDIVIDUAL")
    response = client.get("/api/v1/admin/sermons", headers=headers)
    assert response.status_code == 403


def test_mosque_admin_can_update_mosque_name(client, seeded_accounts):
    from conftest import login_headers

    headers = login_headers(client, "admin", "correct-horse-123")
    profile = client.get("/api/v1/admin/profile", headers=headers)
    assert profile.status_code == 200
    assert profile.json()["name"] == "Central Mosque"

    updated = client.patch(
        "/api/v1/admin/profile",
        headers=headers,
        json={"mosque_name": "Copenhagen Central Mosque"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Copenhagen Central Mosque"
    mosques = client.get("/api/v1/reader/mosques").json()
    updated_public_profile = next(
        mosque for mosque in mosques if mosque["id"] == seeded_accounts["mosque_id"]
    )
    assert updated_public_profile["name"] == "Copenhagen Central Mosque"


def test_mosque_name_change_rejects_existing_name(client, seeded_accounts):
    from conftest import login_headers

    headers = login_headers(client, "admin", "correct-horse-123")
    response = client.patch(
        "/api/v1/admin/profile",
        headers=headers,
        json={"mosque_name": "north mosque"},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Mosque name is already registered"


def test_mosque_admin_can_change_password(client, seeded_accounts):
    from conftest import login_headers

    headers = login_headers(client, "admin", "correct-horse-123")
    wrong_current = client.put(
        "/api/v1/admin/password",
        headers=headers,
        json={"current_password": "incorrect", "new_password": "new-password"},
    )
    assert wrong_current.status_code == 400
    assert wrong_current.json()["detail"] == "Current password is incorrect"

    changed = client.put(
        "/api/v1/admin/password",
        headers=headers,
        json={"current_password": "correct-horse-123", "new_password": "new-password"},
    )
    assert changed.status_code == 204

    old_login = client.post(
        "/api/v1/auth/login",
        json={
            "username": "admin",
            "password": "correct-horse-123",
            "account_type": "MOSQUE",
        },
    )
    assert old_login.status_code == 401
    assert login_headers(client, "admin", "new-password")


def test_reader_cannot_change_mosque_profile_or_password(client, seeded_accounts):
    from conftest import login_headers

    headers = login_headers(client, "reader", "reader-password-123", "INDIVIDUAL")
    assert client.get("/api/v1/admin/profile", headers=headers).status_code == 403
    response = client.put(
        "/api/v1/admin/password",
        headers=headers,
        json={"current_password": "reader-password-123", "new_password": "reader-new"},
    )
    assert response.status_code == 403
