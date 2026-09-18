import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models import Mosque, User, UserRole
from app.schemas.auth import (
    LoginRequest,
    MosqueRegisterRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> User:
    username = payload.username.strip().lower()
    exists = db.scalar(
        select(User.id).where(
            func.lower(User.username) == username,
            User.role == UserRole.READER,
        )
    )
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "Username is already registered")
    user = User(
        username=username,
        display_name=payload.display_name.strip(),
        password_hash=hash_password(payload.password),
        role=UserRole.READER,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post(
    "/register-mosque",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_mosque(payload: MosqueRegisterRequest, db: Session = Depends(get_db)) -> User:
    expected_password = get_settings().mosque_registration_password.get_secret_value()
    supplied_password = payload.permission_password.get_secret_value()
    if not secrets.compare_digest(supplied_password, expected_password):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid mosque permission password")

    username = payload.username.strip().lower()
    username_exists = db.scalar(
        select(User.id).where(
            func.lower(User.username) == username,
            User.role.in_([UserRole.MOSQUE_ADMIN, UserRole.SUPER_ADMIN]),
        )
    )
    if username_exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "Mosque username is already registered")

    mosque_name = payload.mosque_name.strip()
    mosque_exists = db.scalar(
        select(Mosque.id).where(func.lower(Mosque.name) == mosque_name.lower())
    )
    if mosque_exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "Mosque name is already registered")

    mosque = Mosque(
        name=mosque_name,
        city=payload.city.strip(),
        country=payload.country.upper(),
    )
    db.add(mosque)
    db.flush()
    user = User(
        username=username,
        display_name=payload.admin_display_name.strip(),
        password_hash=hash_password(payload.password),
        role=UserRole.MOSQUE_ADMIN,
        mosque_id=mosque.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    roles = (
        [UserRole.READER]
        if payload.account_type == "INDIVIDUAL"
        else [UserRole.MOSQUE_ADMIN, UserRole.SUPER_ADMIN]
    )
    user = db.scalar(
        select(User).where(
            func.lower(User.username) == payload.username.strip().lower(),
            User.role.in_(roles),
        )
    )
    if (
        user is None
        or not user.is_active
        or not verify_password(payload.password, user.password_hash)
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    return TokenResponse(
        access_token=create_access_token(user.id, {"role": user.role, "mosque_id": user.mosque_id})
    )


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)) -> User:
    return user
