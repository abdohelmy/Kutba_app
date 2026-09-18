from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models import SermonStatus, VerificationStatus


class MosqueResponse(BaseModel):
    id: str
    name: str
    city: str
    country: str

    model_config = {"from_attributes": True}


class CitationResponse(BaseModel):
    chunk_id: str
    source_id: str
    title: str
    authority: str
    excerpt: str
    arabic_excerpt: str | None = None
    transliteration: str | None = None
    display_reference: str | None = None
    source_kind: str = "canonical"
    url: str | None = None
    translation_start: int | None = None
    translation_end: int | None = None
    arabic_start: int | None = None
    arabic_end: int | None = None
    anchor_valid: bool = True


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


class GlossaryTermResponse(BaseModel):
    arabic_term: str
    meaning: str
    literal_translation: str
    display_term: str
    alternative_context_meanings: str = ""
    translation_start: int | None = None
    translation_end: int | None = None


class MosqueGlossaryTermRequest(BaseModel):
    arabic_term: str = Field(min_length=1, max_length=250)
    meaning: str = Field(min_length=3, max_length=4000)
    literal_translation: str = Field(min_length=1, max_length=500)
    arabic_variations: str = Field(default="", max_length=4000)
    alternative_context_meanings: str = Field(default="", max_length=4000)


class MosqueGlossaryTermResponse(BaseModel):
    id: str
    arabic_term: str
    meaning: str
    literal_translation: str
    arabic_variations: str = ""
    alternative_context_meanings: str = ""

    model_config = {"from_attributes": True}


class ReaderSegmentResponse(BaseModel):
    id: str
    ordinal: int
    translated_text: str
    citations: list[CitationResponse]
    glossary_terms: list[GlossaryTermResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ReaderSermonDetailResponse(SermonSummaryResponse):
    segments: list[ReaderSegmentResponse]


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
