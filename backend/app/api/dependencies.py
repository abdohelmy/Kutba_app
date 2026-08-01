from collections.abc import Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import User, UserRole

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = payload.get("sub")
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from exc
    user = db.get(User, user_id) if user_id else None
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User is inactive or missing")
    return user


def require_roles(*roles: UserRole) -> Callable:
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
        return user

    return dependency


def require_mosque_admin(
    user: User = Depends(require_roles(UserRole.MOSQUE_ADMIN, UserRole.SUPER_ADMIN)),
) -> User:
    if user.role == UserRole.MOSQUE_ADMIN and not user.mosque_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin is not assigned to a mosque")
    return user


def assert_mosque_access(user: User, mosque_id: str) -> None:
    if user.role != UserRole.SUPER_ADMIN and user.mosque_id != mosque_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This mosque is outside your scope")
