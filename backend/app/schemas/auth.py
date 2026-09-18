from typing import Literal

from pydantic import BaseModel, Field, SecretStr

from app.models import UserRole


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    display_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=6, max_length=128)


class MosqueRegisterRequest(BaseModel):
    mosque_name: str = Field(min_length=2, max_length=200)
    city: str = Field(min_length=2, max_length=120)
    country: str = Field(min_length=2, max_length=2, pattern=r"^[A-Za-z]{2}$")
    admin_display_name: str = Field(min_length=2, max_length=120)
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(min_length=6, max_length=128)
    permission_password: SecretStr


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str
    account_type: Literal["INDIVIDUAL", "MOSQUE"]


class MosqueProfileUpdateRequest(BaseModel):
    mosque_name: str = Field(min_length=2, max_length=200)


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

    model_config = {"from_attributes": True}
