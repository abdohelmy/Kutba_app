from datetime import UTC, date, datetime

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.dependencies import assert_mosque_access, require_mosque_admin
from app.db.session import get_db
from app.models import (
    Sermon,
    SermonSegment,
    SermonStatus,
    SourceChunk,
    TrustedSource,
    User,
    UserRole,
    VerificationStatus,
)
from app.schemas.content import (
    PublishResponse,
    SegmentResponse,
    SegmentReviewRequest,
    SermonDetailResponse,
    SermonSummaryResponse,
    SourceResponse,
    SourceTextReviewRequest,
    TranslationQueuedResponse,
)
from app.services.documents import (
    chunk_reference_text,
    extract_document_text,
    read_document_upload,
    remove_stored_file,
    split_text,
    store_document,
    validate_arabic_text,
)
from app.services.ocr import OcrProcessingError, OcrUnavailableError
from app.services.translation import run_translation_job

router = APIRouter(prefix="/admin", tags=["admin"])


def resolve_admin_mosque(user: User, requested_mosque_id: str | None) -> str:
    mosque_id = requested_mosque_id if user.role == UserRole.SUPER_ADMIN else user.mosque_id
    if not mosque_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A mosque_id is required")
    assert_mosque_access(user, mosque_id)
    return mosque_id


def load_admin_sermon(db: Session, user: User, sermon_id: str) -> Sermon:
    sermon = db.scalar(
        select(Sermon).options(selectinload(Sermon.segments)).where(Sermon.id == sermon_id)
    )
    if sermon is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sermon not found")
    assert_mosque_access(user, sermon.mosque_id)
    return sermon


@router.post("/sources", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
async def upload_trusted_source(
    title: str = Form(min_length=2, max_length=250),
    authority: str = Form(min_length=2, max_length=250),
    language: str = Form(min_length=2, max_length=16),
    mosque_id: str | None = Form(default=None),
    file: UploadFile = File(),
    user: User = Depends(require_mosque_admin),
    db: Session = Depends(get_db),
) -> TrustedSource:
    resolved_mosque_id = resolve_admin_mosque(user, mosque_id)
    document = await read_document_upload(file)
    try:
        text = extract_document_text(document)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    file_path, digest = store_document(document, "sources")
    try:
        source = TrustedSource(
            mosque_id=resolved_mosque_id,
            title=title.strip(),
            authority=authority.strip(),
            language=language.lower(),
            file_path=file_path,
            sha256=digest,
        )
        db.add(source)
        db.flush()
        db.add_all(
            SourceChunk(source_id=source.id, ordinal=index, text=value)
            for index, value in enumerate(chunk_reference_text(text))
        )
        db.commit()
        db.refresh(source)
        return source
    except Exception:
        db.rollback()
        remove_stored_file(file_path)
        raise


@router.get("/sources", response_model=list[SourceResponse])
def list_sources(
    mosque_id: str | None = None,
    user: User = Depends(require_mosque_admin),
    db: Session = Depends(get_db),
) -> list[TrustedSource]:
    resolved_mosque_id = resolve_admin_mosque(user, mosque_id)
    return list(
        db.scalars(
            select(TrustedSource)
            .where(TrustedSource.mosque_id == resolved_mosque_id)
            .order_by(TrustedSource.created_at.desc())
        )
    )


@router.post("/sermons", response_model=SermonSummaryResponse, status_code=status.HTTP_201_CREATED)
async def upload_sermon(
    title: str = Form(min_length=2, max_length=250),
    khutba_date: date = Form(),
    target_language: str = Form(min_length=2, max_length=16),
    mosque_id: str | None = Form(default=None),
    file: UploadFile = File(),
    user: User = Depends(require_mosque_admin),
    db: Session = Depends(get_db),
) -> Sermon:
    resolved_mosque_id = resolve_admin_mosque(user, mosque_id)
    document = await read_document_upload(file)
    try:
        arabic_text = extract_document_text(
            document,
            require_arabic=True,
            allow_ocr=True,
        )
    except OcrUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except OcrProcessingError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    file_path, digest = store_document(document, "sermons")
    try:
        sermon = Sermon(
            mosque_id=resolved_mosque_id,
            title=title.strip(),
            khutba_date=khutba_date,
            target_language=target_language.lower(),
            source_file_path=file_path,
            source_file_sha256=digest,
            arabic_text=arabic_text,
            status=SermonStatus.SOURCE_REVIEW_REQUIRED,
            created_by=user.id,
        )
        sermon.segments = [
            SermonSegment(ordinal=index, arabic_text=value)
            for index, value in enumerate(split_text(arabic_text))
        ]
        db.add(sermon)
        db.commit()
        db.refresh(sermon)
        return sermon
    except Exception:
        db.rollback()
        remove_stored_file(file_path)
        raise


@router.get("/sermons", response_model=list[SermonSummaryResponse])
def list_admin_sermons(
    mosque_id: str | None = None,
    user: User = Depends(require_mosque_admin),
    db: Session = Depends(get_db),
) -> list[Sermon]:
    resolved_mosque_id = resolve_admin_mosque(user, mosque_id)
    return list(
        db.scalars(
            select(Sermon)
            .where(Sermon.mosque_id == resolved_mosque_id)
            .order_by(Sermon.khutba_date.desc())
        )
    )


@router.get("/sermons/{sermon_id}", response_model=SermonDetailResponse)
def get_admin_sermon(
    sermon_id: str,
    user: User = Depends(require_mosque_admin),
    db: Session = Depends(get_db),
) -> Sermon:
    return load_admin_sermon(db, user, sermon_id)


@router.put("/sermons/{sermon_id}/source-text", response_model=SermonDetailResponse)
def confirm_source_text(
    sermon_id: str,
    payload: SourceTextReviewRequest,
    user: User = Depends(require_mosque_admin),
    db: Session = Depends(get_db),
) -> Sermon:
    sermon = load_admin_sermon(db, user, sermon_id)
    if sermon.status != SermonStatus.SOURCE_REVIEW_REQUIRED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "The extracted source text is not awaiting review",
        )
    arabic_text = payload.arabic_text.strip()
    try:
        validate_arabic_text(arabic_text)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    sermon.arabic_text = arabic_text
    sermon.segments.clear()
    db.flush()
    sermon.segments = [
        SermonSegment(ordinal=index, arabic_text=value)
        for index, value in enumerate(split_text(arabic_text))
    ]
    sermon.status = SermonStatus.DRAFT
    sermon.failure_reason = None
    db.commit()
    return sermon


@router.post("/sermons/{sermon_id}/translate", response_model=TranslationQueuedResponse)
def translate_sermon(
    sermon_id: str,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_mosque_admin),
    db: Session = Depends(get_db),
) -> TranslationQueuedResponse:
    sermon = load_admin_sermon(db, user, sermon_id)
    if sermon.status not in {SermonStatus.DRAFT, SermonStatus.FAILED}:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"A sermon in {sermon.status} state cannot start translation",
        )
    source_exists = db.scalar(
        select(TrustedSource.id).where(TrustedSource.mosque_id == sermon.mosque_id).limit(1)
    )
    if not source_exists:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Upload at least one trusted source before translation",
        )
    sermon.status = SermonStatus.TRANSLATING
    sermon.failure_reason = None
    db.commit()
    background_tasks.add_task(run_translation_job, sermon.id)
    return TranslationQueuedResponse(id=sermon.id, status=SermonStatus.TRANSLATING)


@router.patch("/sermons/{sermon_id}/segments/{segment_id}", response_model=SegmentResponse)
def review_segment(
    sermon_id: str,
    segment_id: str,
    payload: SegmentReviewRequest,
    user: User = Depends(require_mosque_admin),
    db: Session = Depends(get_db),
) -> SermonSegment:
    sermon = load_admin_sermon(db, user, sermon_id)
    if sermon.status != SermonStatus.REVIEW_REQUIRED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Sermon is not awaiting review")
    segment = next((item for item in sermon.segments if item.id == segment_id), None)
    if segment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Segment not found")
    if payload.translated_text is not None:
        segment.translated_text = payload.translated_text.strip()
    if not segment.translated_text:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Translation is required")
    segment.reviewer_note = payload.reviewer_note
    segment.reviewed_by = user.id if payload.approved else None
    segment.verification_status = (
        VerificationStatus.HUMAN_APPROVED if payload.approved else VerificationStatus.FLAGGED
    )
    db.commit()
    db.refresh(segment)
    return segment


@router.post("/sermons/{sermon_id}/publish", response_model=PublishResponse)
def publish_sermon(
    sermon_id: str,
    user: User = Depends(require_mosque_admin),
    db: Session = Depends(get_db),
) -> PublishResponse:
    sermon = load_admin_sermon(db, user, sermon_id)
    if sermon.status != SermonStatus.REVIEW_REQUIRED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Sermon is not ready for publication")
    unapproved = [
        segment.ordinal
        for segment in sermon.segments
        if segment.verification_status != VerificationStatus.HUMAN_APPROVED
        or not segment.translated_text
    ]
    if unapproved:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Every segment needs human approval; pending ordinals: {unapproved}",
        )
    sermon.status = SermonStatus.PUBLISHED
    sermon.published_at = datetime.now(UTC)
    db.commit()
    return PublishResponse(
        id=sermon.id, status=SermonStatus.PUBLISHED, published_at=sermon.published_at
    )
