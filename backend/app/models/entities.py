from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin


class UserRole(StrEnum):
    SUPER_ADMIN = "SUPER_ADMIN"
    MOSQUE_ADMIN = "MOSQUE_ADMIN"
    READER = "READER"


class SermonStatus(StrEnum):
    SOURCE_REVIEW_REQUIRED = "SOURCE_REVIEW_REQUIRED"
    DRAFT = "DRAFT"
    TRANSLATING = "TRANSLATING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    PUBLISHED = "PUBLISHED"
    HIDDEN = "HIDDEN"
    FAILED = "FAILED"


class VerificationStatus(StrEnum):
    PENDING = "PENDING"
    PASSED = "PASSED"
    FLAGGED = "FLAGGED"
    HUMAN_APPROVED = "HUMAN_APPROVED"


class Mosque(Base, IdMixin, TimestampMixin):
    __tablename__ = "mosques"

    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    city: Mapped[str] = mapped_column(String(120), index=True)
    country: Mapped[str] = mapped_column(String(2), default="DK")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class MosqueGlossaryTerm(Base, IdMixin, TimestampMixin):
    __tablename__ = "mosque_glossary_terms"
    __table_args__ = (
        UniqueConstraint("mosque_id", "normalized_term", name="uq_mosque_glossary_term"),
    )

    mosque_id: Mapped[str] = mapped_column(ForeignKey("mosques.id"), index=True)
    arabic_term: Mapped[str] = mapped_column(String(250))
    normalized_term: Mapped[str] = mapped_column(String(250))
    meaning: Mapped[str] = mapped_column(Text)
    literal_translation: Mapped[str] = mapped_column(String(500))
    arabic_variations: Mapped[str] = mapped_column(Text, default="")
    alternative_context_meanings: Mapped[str] = mapped_column(Text, default="")


class User(Base, IdMixin, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_username", "email"),
        Index("uq_users_username_role", "email", "role", unique=True),
    )

    # The physical column keeps its legacy name so existing development databases can be migrated
    # without rebuilding foreign-key relationships. The public API exposes only `username`.
    username: Mapped[str] = mapped_column("email", String(64))
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(String(32), default=UserRole.READER)
    mosque_id: Mapped[str | None] = mapped_column(ForeignKey("mosques.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    mosque: Mapped[Mosque | None] = relationship()


class Sermon(Base, IdMixin, TimestampMixin):
    __tablename__ = "sermons"

    mosque_id: Mapped[str] = mapped_column(ForeignKey("mosques.id"), index=True)
    title: Mapped[str] = mapped_column(String(250))
    title_is_inferred: Mapped[bool] = mapped_column(Boolean, default=False)
    khutba_date: Mapped[date] = mapped_column(Date, index=True)
    target_language: Mapped[str] = mapped_column(String(16))
    # Keep the original database column names so existing development databases remain readable.
    source_file_path: Mapped[str] = mapped_column("source_pdf_path", String(500))
    source_file_sha256: Mapped[str] = mapped_column("source_pdf_sha256", String(64))
    arabic_text: Mapped[str] = mapped_column(Text)
    status: Mapped[SermonStatus] = mapped_column(String(32), default=SermonStatus.DRAFT)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    provider_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    segments: Mapped[list["SermonSegment"]] = relationship(
        back_populates="sermon",
        cascade="all, delete-orphan",
        order_by="SermonSegment.ordinal",
    )


class SermonSegment(Base, IdMixin, TimestampMixin):
    __tablename__ = "sermon_segments"
    __table_args__ = (UniqueConstraint("sermon_id", "ordinal"),)

    sermon_id: Mapped[str] = mapped_column(ForeignKey("sermons.id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    arabic_text: Mapped[str] = mapped_column(Text)
    translated_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        String(32), default=VerificationStatus.PENDING
    )
    issues: Mapped[list[str]] = mapped_column(JSON, default=list)
    citations: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)
    reviewer_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    sermon: Mapped[Sermon] = relationship(back_populates="segments")
