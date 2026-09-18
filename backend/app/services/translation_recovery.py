from sqlalchemy import update

from app.db.session import SessionLocal
from app.models import Sermon, SermonStatus


def recover_interrupted_translations() -> None:
    """The deployment runs one API worker. Make interrupted jobs explicitly retryable."""
    with SessionLocal() as db:
        db.execute(
            update(Sermon)
            .where(Sermon.status == SermonStatus.TRANSLATING)
            .values(
                status=SermonStatus.FAILED,
                failure_reason=(
                    "Translation was interrupted by a server restart. "
                    "Retry to continue from the saved sections."
                ),
            )
        )
        db.commit()
