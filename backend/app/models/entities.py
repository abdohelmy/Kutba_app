from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
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


class User(Base, IdMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(String(32), default=UserRole.READER)
    mosque_id: Mapped[str | None] = mapped_column(ForeignKey("mosques.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    mosque: Mapped[Mosque | None] = relationship()


class TrustedSource(Base, IdMixin, TimestampMixin):
    __tablename__ = "trusted_sources"

    mosque_id: Mapped[str] = mapped_column(ForeignKey("mosques.id"), index=True)
    title: Mapped[str] = mapped_column(String(250))
    authority: Mapped[str] = mapped_column(String(250))
    language: Mapped[str] = mapped_column(String(16))
    file_path: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str] = mapped_column(String(64))

    chunks: Mapped[list["SourceChunk"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )


class SourceChunk(Base, IdMixin):
    __tablename__ = "source_chunks"
    __table_args__ = (UniqueConstraint("source_id", "ordinal"),)

    source_id: Mapped[str] = mapped_column(ForeignKey("trusted_sources.id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)

    source: Mapped[TrustedSource] = relationship(back_populates="chunks")


class Sermon(Base, IdMixin, TimestampMixin):
    __tablename__ = "sermons"

    mosque_id: Mapped[str] = mapped_column(ForeignKey("mosques.id"), index=True)
    title: Mapped[str] = mapped_column(String(250))
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
