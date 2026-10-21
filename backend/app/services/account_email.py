"""Account emails. Tokens are hashed in storage and never logged."""

import hashlib
import logging
import secrets
import smtplib
import ssl
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Mosque, User, UserRole
from app.models.entities import PasswordReset

logger = logging.getLogger(__name__)


def email_ready() -> bool:
    settings = get_settings()
    return bool(settings.smtp_host and settings.smtp_from)


def send_email(address: str, subject: str, body: str) -> bool:
    settings = get_settings()
    if not email_ready():
        return False
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = address
    message["Subject"] = subject
    message.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
            smtp.send_message(message)
        return True
    except (OSError, smtplib.SMTPException):
        logger.warning("Account email delivery failed")
        return False


def reset_link(db: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    db.execute(update(PasswordReset).where(PasswordReset.user_id == user.id).values(used=True))
    db.add(
        PasswordReset(
            user_id=user.id,
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=30),
        )
    )
    db.flush()
    return get_settings().public_web_url.rstrip("/") + "/#reset/" + token


def notify_registration(db: Session, mosque: Mosque) -> None:
    for owner in db.scalars(
        select(User).where(
            User.role == UserRole.SUPER_ADMIN,
            User.is_active.is_(True),
            User.contact_email.is_not(None),
        )
    ):
        send_email(
            owner.contact_email,
            "Mosque approval requested",
            f"{mosque.name} ({mosque.city}) requested an account.\n\n"
            f"Review it at {get_settings().public_web_url}/#owner",
        )
