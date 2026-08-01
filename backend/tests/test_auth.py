from app.models import UserRole


def test_reader_can_register_login_and_access_mosques(client):
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": "new.reader@example.com",
            "display_name": "New Reader",
            "password": "a-secure-reader-password",
        },
    )
    assert register.status_code == 201
    assert register.json()["role"] == UserRole.READER

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "new.reader@example.com", "password": "a-secure-reader-password"},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/api/v1/reader/mosques", headers=headers).status_code == 200


def test_reader_routes_require_authentication(client):
    response = client.get("/api/v1/reader/mosques")
    assert response.status_code == 401


def test_reader_cannot_access_admin_routes(client, seeded_accounts):
    from conftest import login_headers

    headers = login_headers(client, "reader@example.com", "reader-password-123")
    response = client.get("/api/v1/admin/sermons", headers=headers)
    assert response.status_code == 403
