import argparse

from sqlalchemy import select

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import Mosque, User, UserRole


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or update the first mosque admin")
    parser.add_argument("--mosque", required=True)
    parser.add_argument("--city", required=True)
    parser.add_argument("--country", default="DK")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--password", required=True)
    args = parser.parse_args()
    if len(args.password) < 10:
        parser.error("--password must contain at least 10 characters")

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        mosque = db.scalar(select(Mosque).where(Mosque.name == args.mosque))
        if mosque is None:
            mosque = Mosque(name=args.mosque, city=args.city, country=args.country.upper())
            db.add(mosque)
            db.flush()
        user = db.scalar(select(User).where(User.email == args.email.lower()))
        if user is None:
            user = User(email=args.email.lower())
            db.add(user)
        user.display_name = args.name
        user.password_hash = hash_password(args.password)
        user.role = UserRole.MOSQUE_ADMIN
        user.mosque_id = mosque.id
        user.is_active = True
        db.commit()
        print(f"Admin {user.email} is assigned to {mosque.name} ({mosque.id})")


if __name__ == "__main__":
    main()
