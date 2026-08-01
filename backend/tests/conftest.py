import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TEST_ROOT = Path(__file__).parent / ".runtime"
TEST_ROOT.mkdir(exist_ok=True)
os.environ["KHUTBA_DATABASE_URL"] = f"sqlite:///{TEST_ROOT / 'test.db'}"
os.environ["KHUTBA_STORAGE_DIR"] = str(TEST_ROOT / "data")
os.environ["KHUTBA_TRANSLATION_PROVIDER"] = "mock"
os.environ["KHUTBA_SECRET_KEY"] = "test-secret-key-that-is-long-enough-12345"
os.environ["KHUTBA_CANONICAL_SOURCES_ENABLED"] = "false"

from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Mosque, User, UserRole  # noqa: E402


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def seeded_accounts():
    with SessionLocal() as db:
        mosque = Mosque(name="Central Mosque", city="Copenhagen", country="DK")
        other_mosque = Mosque(name="North Mosque", city="Aarhus", country="DK")
        db.add_all([mosque, other_mosque])
        db.flush()
        admin = User(
            email="admin@example.com",
            display_name="Mosque Reviewer",
            password_hash=hash_password("correct-horse-123"),
            role=UserRole.MOSQUE_ADMIN,
            mosque_id=mosque.id,
        )
        reader = User(
            email="reader@example.com",
            display_name="Reader",
            password_hash=hash_password("reader-password-123"),
            role=UserRole.READER,
        )
        db.add_all([admin, reader])
        db.commit()
        return {
            "mosque_id": mosque.id,
            "other_mosque_id": other_mosque.id,
            "admin_id": admin.id,
            "reader_id": reader.id,
        }


def login_headers(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
