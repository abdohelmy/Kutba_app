from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models import SermonStatus, VerificationStatus


class MosqueResponse(BaseModel):
    id: str
    name: str
    city: str
    country: str

    model_config = {"from_attributes": True}


class SourceResponse(BaseModel):
    id: str
    title: str
    authority: str
    language: str
    sha256: str
    created_at: datetime

    model_config = {"from_attributes": True}


class CitationResponse(BaseModel):
    chunk_id: str
    source_id: str
    title: str
    authority: str
    excerpt: str
    source_kind: str = "mosque"
    url: str | None = None


class SegmentResponse(BaseModel):
    id: str
    ordinal: int
    arabic_text: str
    translated_text: str | None
    verification_status: VerificationStatus
    issues: list[str]
    citations: list[CitationResponse]
    reviewer_note: str | None

    model_config = {"from_attributes": True}


class SermonSummaryResponse(BaseModel):
    id: str
    mosque_id: str
    title: str
    khutba_date: date
    target_language: str
    status: SermonStatus
    provider_name: str | None
    model_name: str | None
    failure_reason: str | None
    published_at: datetime | None

    model_config = {"from_attributes": True}


class SermonDetailResponse(SermonSummaryResponse):
    segments: list[SegmentResponse]


class SegmentReviewRequest(BaseModel):
    translated_text: str | None = Field(default=None, min_length=1)
    approved: bool
    reviewer_note: str | None = Field(default=None, max_length=2000)


class SourceTextReviewRequest(BaseModel):
    arabic_text: str = Field(min_length=40, max_length=500_000)


class PublishResponse(BaseModel):
    id: str
    status: SermonStatus
    published_at: datetime


class TranslationQueuedResponse(BaseModel):
    id: str
    status: SermonStatus
