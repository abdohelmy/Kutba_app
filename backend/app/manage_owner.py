"""Run on the server: python -m app.manage_owner --username abdo --email ..."""

import argparse
import secrets

from sqlalchemy import func, select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import User, UserRole
from app.services.account_email import reset_link


def main():
    parser = argparse.ArgumentParser(
        description="Create the initial owner and print a one-time setup link"
    )
    parser.add_argument("--username", required=True)
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    with SessionLocal() as db:
        if db.scalar(select(User.id).where(User.role == UserRole.SUPER_ADMIN)):
            raise SystemExit("An owner already exists. Use password recovery instead.")
        if db.scalar(
            select(User.id).where(
                func.lower(User.username) == args.username.lower(),
                User.role == UserRole.MOSQUE_ADMIN,
            )
        ):
            raise SystemExit("This username belongs to a mosque admin; choose another username.")
        user = User(
            username=args.username.lower(),
            display_name="App owner",
            contact_email=args.email,
            role=UserRole.SUPER_ADMIN,
            password_hash=hash_password(secrets.token_urlsafe(48)),
        )
        db.add(user)
        db.flush()
        link = reset_link(db, user)
        db.commit()
        print(link)


if __name__ == "__main__":
    main()
