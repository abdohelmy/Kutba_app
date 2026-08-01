from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models import Mosque, Sermon, SermonStatus
from app.schemas.content import MosqueResponse, SermonDetailResponse, SermonSummaryResponse

router = APIRouter(prefix="/reader", tags=["reader"], dependencies=[Depends(get_current_user)])


@router.get("/mosques", response_model=list[MosqueResponse])
def list_mosques(db: Session = Depends(get_db)) -> list[Mosque]:
    return list(
        db.scalars(
            select(Mosque).where(Mosque.is_active.is_(True)).order_by(Mosque.city, Mosque.name)
        )
    )


@router.get("/mosques/{mosque_id}/sermons", response_model=list[SermonSummaryResponse])
def list_published_sermons(
    mosque_id: str,
    language: str | None = Query(default=None, min_length=2, max_length=16),
    db: Session = Depends(get_db),
) -> list[Sermon]:
    query = (
        select(Sermon)
        .where(Sermon.mosque_id == mosque_id, Sermon.status == SermonStatus.PUBLISHED)
        .order_by(Sermon.khutba_date.desc())
    )
    if language:
        query = query.where(Sermon.target_language == language)
    return list(db.scalars(query))


@router.get("/sermons/{sermon_id}", response_model=SermonDetailResponse)
def get_published_sermon(sermon_id: str, db: Session = Depends(get_db)) -> Sermon:
    sermon = db.scalar(
        select(Sermon)
        .options(selectinload(Sermon.segments))
        .where(Sermon.id == sermon_id, Sermon.status == SermonStatus.PUBLISHED)
    )
    if sermon is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Published sermon not found")
    return sermon
