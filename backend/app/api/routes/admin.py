from datetime import UTC, date, datetime

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from app.api.dependencies import assert_mosque_access, require_mosque_admin
from app.core.security import hash_password, verify_password
from app.db.session import get_db
from app.models import (
    Mosque,
    MosqueGlossaryTerm,
    Sermon,
    SermonSegment,
    SermonStatus,
    User,
    UserRole,
    VerificationStatus,
)
from app.schemas.auth import MosqueProfileUpdateRequest, PasswordChangeRequest
from app.schemas.content import (
    MosqueGlossaryTermRequest,
    MosqueGlossaryTermResponse,
    MosqueResponse,
    PublishResponse,
    ReaderSermonDetailResponse,
    SegmentResponse,
    SegmentReviewRequest,
    SermonDetailResponse,
    SermonSummaryResponse,
    SourceTextReviewRequest,
    TranslationQueuedResponse,
)
from app.services.citation_edits import REVIEW_PREFIX, reanchor_citations
from app.services.documents import (
    extract_document_text,
    read_document_upload,
    remove_stored_file,
    split_text,
    store_document,
    validate_arabic_text,
)
from app.services.glossary import build_glossary_entry, normalized_arabic_key
from app.services.ocr import OcrProcessingError, OcrUnavailableError
from app.services.sermon_titles import infer_source_title
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


def load_admin_mosque(db: Session, user: User) -> Mosque:
    if not user.mosque_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This admin is not assigned to a mosque")
    mosque = db.get(Mosque, user.mosque_id)
    if mosque is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mosque not found")
    return mosque


def load_admin_glossary_term(
    db: Session, user: User, glossary_term_id: str
) -> MosqueGlossaryTerm:
    mosque = load_admin_mosque(db, user)
    term = db.get(MosqueGlossaryTerm, glossary_term_id)
    if term is None or term.mosque_id != mosque.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Glossary term not found")
    return term


def glossary_values(payload: MosqueGlossaryTermRequest) -> dict[str, str]:
    try:
        entry = build_glossary_entry(
            arabic_term=payload.arabic_term,
            meaning=payload.meaning,
            literal_translation=payload.literal_translation,
            arabic_variations=payload.arabic_variations,
            alternative_context_meanings=payload.alternative_context_meanings,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return {
        "arabic_term": entry.arabic_term,
        "normalized_term": normalized_arabic_key(entry.arabic_term),
        "meaning": entry.meaning,
        "literal_translation": entry.literal_translation,
        "arabic_variations": payload.arabic_variations.strip(),
        "alternative_context_meanings": entry.alternative_context_meanings,
    }


def assert_unique_glossary_term(
    db: Session,
    mosque_id: str,
    normalized_term: str,
    excluding_id: str | None = None,
) -> None:
    query = select(MosqueGlossaryTerm.id).where(
        MosqueGlossaryTerm.mosque_id == mosque_id,
        MosqueGlossaryTerm.normalized_term == normalized_term,
    )
    if excluding_id:
        query = query.where(MosqueGlossaryTerm.id != excluding_id)
    if db.scalar(query):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This mosque already has a glossary entry for that Arabic term",
        )


@router.get("/profile", response_model=MosqueResponse)
def get_mosque_profile(
    user: User = Depends(require_mosque_admin),
    db: Session = Depends(get_db),
) -> Mosque:
    return load_admin_mosque(db, user)


@router.patch("/profile", response_model=MosqueResponse)
def update_mosque_profile(
    payload: MosqueProfileUpdateRequest,
    user: User = Depends(require_mosque_admin),
    db: Session = Depends(get_db),
) -> Mosque:
    mosque = load_admin_mosque(db, user)
    mosque_name = payload.mosque_name.strip()
    duplicate = db.scalar(
        select(Mosque.id).where(
            func.lower(Mosque.name) == mosque_name.lower(),
            Mosque.id != mosque.id,
        )
    )
    if duplicate:
        raise HTTPException(status.HTTP_409_CONFLICT, "Mosque name is already registered")
    mosque.name = mosque_name
    db.commit()
    db.refresh(mosque)
    return mosque


@router.put("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_mosque_admin_password(
    payload: PasswordChangeRequest,
    user: User = Depends(require_mosque_admin),
    db: Session = Depends(get_db),
) -> Response:
    current_password = payload.current_password.get_secret_value()
    if not verify_password(current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    user.password_hash = hash_password(payload.new_password.get_secret_value())
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/glossary", response_model=list[MosqueGlossaryTermResponse])
def list_mosque_glossary(
    user: User = Depends(require_mosque_admin),
    db: Session = Depends(get_db),
) -> list[MosqueGlossaryTerm]:
    mosque = load_admin_mosque(db, user)
    return list(
        db.scalars(
            select(MosqueGlossaryTerm)
            .where(MosqueGlossaryTerm.mosque_id == mosque.id)
            .order_by(MosqueGlossaryTerm.created_at.desc())
        )
    )


@router.post(
    "/glossary",
    response_model=MosqueGlossaryTermResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_mosque_glossary_term(
    payload: MosqueGlossaryTermRequest,
    user: User = Depends(require_mosque_admin),
    db: Session = Depends(get_db),
) -> MosqueGlossaryTerm:
    mosque = load_admin_mosque(db, user)
    values = glossary_values(payload)
    assert_unique_glossary_term(db, mosque.id, values["normalized_term"])
    term = MosqueGlossaryTerm(mosque_id=mosque.id, **values)
    db.add(term)
    db.commit()
    db.refresh(term)
    return term


@router.put("/glossary/{glossary_term_id}", response_model=MosqueGlossaryTermResponse)
def update_mosque_glossary_term(
    glossary_term_id: str,
    payload: MosqueGlossaryTermRequest,
    user: User = Depends(require_mosque_admin),
    db: Session = Depends(get_db),
) -> MosqueGlossaryTerm:
    term = load_admin_glossary_term(db, user, glossary_term_id)
    values = glossary_values(payload)
    assert_unique_glossary_term(
        db,
        term.mosque_id,
        values["normalized_term"],
        excluding_id=term.id,
    )
    for field, value in values.items():
        setattr(term, field, value)
    db.commit()
    db.refresh(term)
    return term


@router.delete("/glossary/{glossary_term_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_mosque_glossary_term(
    glossary_term_id: str,
    user: User = Depends(require_mosque_admin),
    db: Session = Depends(get_db),
) -> Response:
    term = load_admin_glossary_term(db, user, glossary_term_id)
    db.delete(term)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/sermons", response_model=SermonSummaryResponse, status_code=status.HTTP_201_CREATED)
async def upload_sermon(
    title: str | None = Form(default=None, max_length=250),
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
        supplied_title = title.strip() if title else ""
        sermon = Sermon(
            mosque_id=resolved_mosque_id,
            title=supplied_title or infer_source_title(arabic_text, khutba_date),
            title_is_inferred=not supplied_title,
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


@router.delete("/sermons/{sermon_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_admin_sermon(
    sermon_id: str,
    user: User = Depends(require_mosque_admin),
    db: Session = Depends(get_db),
) -> Response:
    sermon = load_admin_sermon(db, user, sermon_id)
    source_file_path = sermon.source_file_path
    db.delete(sermon)
    db.commit()
    remove_stored_file(source_file_path)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/sermons/{sermon_id}/hide", response_model=SermonSummaryResponse)
def hide_admin_sermon(
    sermon_id: str,
    user: User = Depends(require_mosque_admin),
    db: Session = Depends(get_db),
) -> Sermon:
    sermon = load_admin_sermon(db, user, sermon_id)
    if sermon.status != SermonStatus.PUBLISHED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Only a published khutba can be hidden",
        )
    sermon.status = SermonStatus.HIDDEN
    db.commit()
    return sermon


@router.post("/sermons/{sermon_id}/show", response_model=SermonSummaryResponse)
def show_admin_sermon(
    sermon_id: str,
    user: User = Depends(require_mosque_admin),
    db: Session = Depends(get_db),
) -> Sermon:
    sermon = load_admin_sermon(db, user, sermon_id)
    if sermon.status != SermonStatus.HIDDEN:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Only a hidden khutba can be shown",
        )
    sermon.status = SermonStatus.PUBLISHED
    db.commit()
    return sermon


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
    if sermon.title_is_inferred:
        sermon.title = infer_source_title(arabic_text, sermon.khutba_date)
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
    claimed = db.execute(
        update(Sermon)
        .where(Sermon.id == sermon.id, Sermon.status.in_([SermonStatus.DRAFT, SermonStatus.FAILED]))
        .values(status=SermonStatus.TRANSLATING, failure_reason=None)
    )
    if claimed.rowcount != 1:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Translation is already running")
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
    edited = (
        payload.translated_text.strip()
        if payload.translated_text is not None else segment.translated_text or ""
    )
    citations, citation_issues = reanchor_citations(
        segment.translated_text or "", edited, segment.citations
    )
    if payload.approved and citation_issues:
        raise HTTPException(status.HTTP_409_CONFLICT, "\n".join(citation_issues))
    segment.translated_text = edited
    segment.citations = citations
    segment.issues = [
        issue for issue in segment.issues if not issue.startswith(REVIEW_PREFIX)
    ] + citation_issues
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


@router.get("/sermons/{sermon_id}/preview", response_model=ReaderSermonDetailResponse)
def preview_sermon(
    sermon_id: str,
    user: User = Depends(require_mosque_admin),
    db: Session = Depends(get_db),
) -> ReaderSermonDetailResponse:
    from app.api.routes.reader import _reader_sermon_response

    return _reader_sermon_response(load_admin_sermon(db, user, sermon_id), db)


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
