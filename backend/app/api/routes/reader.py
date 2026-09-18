import re
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models import Mosque, Sermon, SermonStatus
from app.schemas.content import (
    GlossaryTermResponse,
    MosqueResponse,
    ReaderSegmentResponse,
    ReaderSermonDetailResponse,
    SermonSummaryResponse,
)
from app.services.canonical_sources import quran_passage_is_embedded_in_hadith
from app.services.glossary import glossary_matches
from app.services.mosque_glossary import glossary_entries_for_mosque
from app.services.sermon_pdf import build_sermon_pdf

router = APIRouter(prefix="/reader", tags=["reader"])


def _deduplicate_reader_citations(
    citations: list[dict[str, object]],
) -> list[dict[str, object]]:
    hadith_citations = [
        citation for citation in citations if citation.get("source_kind") == "hadith"
    ]
    hadith_arabic = [
        str(citation.get("arabic_excerpt") or "")
        for citation in hadith_citations
        if citation.get("arabic_excerpt")
    ]
    if not hadith_citations:
        return citations
    result: list[dict[str, object]] = []
    for citation in citations:
        if citation.get("source_kind") != "quran":
            result.append(citation)
            continue
        quran_start = citation.get("arabic_start")
        quran_end = citation.get("arabic_end")
        positioned_hadiths = [
            item
            for item in hadith_citations
            if isinstance(item.get("arabic_start"), int) and isinstance(item.get("arabic_end"), int)
        ]
        if isinstance(quran_start, int) and isinstance(quran_end, int):
            embedded_at_same_occurrence = any(
                quran_start < int(item["arabic_end"])
                and int(item["arabic_start"]) < quran_end
                and quran_passage_is_embedded_in_hadith(
                    str(citation.get("arabic_excerpt") or ""),
                    [str(item.get("arabic_excerpt") or "")],
                )
                for item in positioned_hadiths
            )
            if not embedded_at_same_occurrence:
                result.append(citation)
        elif not quran_passage_is_embedded_in_hadith(
            str(citation.get("arabic_excerpt") or ""), hadith_arabic
        ):
            result.append(citation)
    return result


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


def _published_sermon(sermon_id: str, db: Session) -> Sermon:
    sermon = db.scalar(
        select(Sermon)
        .options(selectinload(Sermon.segments))
        .where(Sermon.id == sermon_id, Sermon.status == SermonStatus.PUBLISHED)
    )
    if sermon is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Published sermon not found")
    return sermon


def _reader_sermon_response(sermon: Sermon, db: Session) -> ReaderSermonDetailResponse:
    summary = SermonSummaryResponse.model_validate(sermon)
    glossary_catalog = glossary_entries_for_mosque(db, sermon.mosque_id)
    seen_terms: set[object] = set()
    segments = []
    for segment in sermon.segments:
        translated_text = segment.translated_text or ""
        terms = glossary_matches(
            segment.arabic_text,
            translated_text,
            seen_terms,
            glossary_catalog,
        )
        segments.append(
            ReaderSegmentResponse(
                id=segment.id,
                ordinal=segment.ordinal,
                translated_text=translated_text,
                citations=_deduplicate_reader_citations(segment.citations),
                glossary_terms=[
                    GlossaryTermResponse(
                        arabic_term=match.arabic_term,
                        meaning=match.entry.meaning,
                        literal_translation=match.literal_translation,
                        display_term=match.display_term,
                        alternative_context_meanings=(match.entry.alternative_context_meanings),
                        translation_start=match.translation_start,
                        translation_end=match.translation_end,
                    )
                    for match in terms
                ],
            )
        )
    return ReaderSermonDetailResponse(**summary.model_dump(), segments=segments)


@router.get("/sermons/{sermon_id}", response_model=ReaderSermonDetailResponse)
def get_published_sermon(
    sermon_id: str, db: Session = Depends(get_db)
) -> ReaderSermonDetailResponse:
    return _reader_sermon_response(_published_sermon(sermon_id, db), db)


@router.get("/sermons/{sermon_id}/pdf")
def download_published_sermon_pdf(
    sermon_id: str, db: Session = Depends(get_db)
) -> Response:
    sermon = _published_sermon(sermon_id, db)
    mosque = db.get(Mosque, sermon.mosque_id)
    mosque_name = mosque.name if mosque else "Publishing mosque"
    detail = _reader_sermon_response(sermon, db)
    pdf = build_sermon_pdf(detail, mosque_name)
    ascii_stem = re.sub(r"[^a-z0-9]+", "-", sermon.title.lower()).strip("-") or "khutba"
    ascii_name = f"{ascii_stem}-{sermon.khutba_date.isoformat()}.pdf"
    unicode_name = quote(f"{sermon.title}-{sermon.khutba_date.isoformat()}.pdf")
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{unicode_name}'
            )
        },
    )
