import hashlib
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
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


class RecoveryRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)


class ResetRequest(BaseModel):
    token: str = Field(min_length=32, max_length=128)
    password: str = Field(min_length=6, max_length=128)


@router.post("/forgot-password")
def forgot_password(payload: RecoveryRequest, db: Session = Depends(get_db)):
    from app.models.entities import PasswordReset
    from app.services.account_email import email_ready, reset_link, send_email

    if not email_ready():
        raise HTTPException(
            503, "Email recovery is not configured. Contact the app administrator for a reset link."
        )
    user = db.scalar(
        select(User).where(
            func.lower(User.username) == payload.username.strip().lower(),
            User.role.in_([UserRole.MOSQUE_ADMIN, UserRole.SUPER_ADMIN]),
            User.is_active.is_(True),
        )
    )
    if user and user.contact_email:
        # Avoid repeated deliveries and invalidate old links on issue.
        recent = db.scalar(
            select(PasswordReset.id).where(
                PasswordReset.user_id == user.id,
                PasswordReset.created_at
                > datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=5),
            )
        )
        if not recent:
            link = reset_link(db, user)
            db.commit()
            send_email(
                user.contact_email,
                "Reset your Khutba password",
                f"This link expires in 30 minutes:\n{link}",
            )
    return {"status": "If the account has a recovery email, a reset link has been sent."}


@router.post("/reset-password")
def reset_password(payload: ResetRequest, db: Session = Depends(get_db)):
    from app.models.entities import PasswordReset

    now = datetime.now(UTC).replace(tzinfo=None)
    reset = db.scalar(
        select(PasswordReset).where(
            PasswordReset.token_hash == hashlib.sha256(payload.token.encode()).hexdigest(),
            PasswordReset.used.is_(False),
            PasswordReset.expires_at > now,
        )
    )
    if reset is None:
        raise HTTPException(400, "This link is invalid or expired. Request a new one.")
    account = db.get(User, reset.user_id)
    if not account or not account.is_active:
        raise HTTPException(400, "Account is unavailable")
    # Atomic consume prevents concurrent reuse of the same link.
    consumed = db.execute(
        update(PasswordReset)
        .where(
            PasswordReset.id == reset.id,
            PasswordReset.used.is_(False),
            PasswordReset.expires_at > now,
        )
        .values(used=True)
    )
    if consumed.rowcount != 1:
        db.rollback()
        raise HTTPException(400, "This link has already been used")
    account.password_hash = hash_password(payload.password)
    account.auth_version += 1
    db.commit()
    return {"status": "Password saved. You can now sign in."}


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
        is_active=False,
        approval_status="PENDING",
    )
    db.add(mosque)
    db.flush()
    user = User(
        username=username,
        display_name=payload.admin_display_name.strip(),
        password_hash=hash_password(payload.password),
        role=UserRole.MOSQUE_ADMIN,
        mosque_id=mosque.id,
        contact_email=payload.contact_email,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    from app.services.account_email import notify_registration

    notify_registration(db, mosque)
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
    if user.role == UserRole.MOSQUE_ADMIN and (
        not user.mosque or not user.mosque.is_active or user.mosque.approval_status != "APPROVED"
    ):
        raise HTTPException(
            403,
            "Your mosque account is awaiting approval or suspended. Contact the app administrator.",
        )
    return TokenResponse(
        access_token=create_access_token(
            user.id,
            {"role": user.role, "mosque_id": user.mosque_id, "auth_version": user.auth_version},
        )
    )


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)) -> User:
    return user
