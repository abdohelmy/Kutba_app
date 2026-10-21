from typing import Annotated, Literal

from pydantic import BaseModel, Field, SecretStr, StringConstraints

from app.models import UserRole

DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]
MosqueName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=200)]


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    display_name: DisplayName
    password: str = Field(min_length=6, max_length=128)


class MosqueRegisterRequest(BaseModel):
    mosque_name: MosqueName
    city: DisplayName
    country: str = Field(min_length=2, max_length=2, pattern=r"^[A-Za-z]{2}$")
    admin_display_name: DisplayName
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(min_length=6, max_length=128)
    # Accepted for older native clients, but never used to grant approval.
    permission_password: SecretStr | None = None
    contact_email: str | None = Field(
        default=None, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$"
    )


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str
    account_type: Literal["INDIVIDUAL", "MOSQUE"]


class MosqueProfileUpdateRequest(BaseModel):
    mosque_name: MosqueName
    city: DisplayName | None = None


class PasswordChangeRequest(BaseModel):
    current_password: SecretStr
    new_password: SecretStr = Field(min_length=6, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    username: str
    display_name: str
    role: UserRole
    mosque_id: str | None
    is_active: bool
    contact_email: str | None = None

    model_config = {"from_attributes": True}
