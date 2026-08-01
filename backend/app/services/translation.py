import asyncio

import httpx
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import Sermon, SermonStatus, VerificationStatus
from app.services.canonical_sources import CanonicalSourceService
from app.services.providers import build_provider
from app.services.retrieval import RetrievedSource, retrieve_sources


def _canonical_wording_issues(
    translated_text: str, target_language: str, sources: list[RetrievedSource]
) -> list[str]:
    if target_language.lower() not in {"en", "eng", "english"}:
        return []
    normalized_translation = " ".join(translated_text.split())
    return [
        f"Canonical {source.source_kind} wording from {source.authority} was not copied verbatim"
        for source in sources
        if source.verbatim_required
        and " ".join(source.text.split()) not in normalized_translation
    ]


async def run_translation_job(sermon_id: str) -> None:
    """Fail-closed background job: completion always requires human review."""
    with SessionLocal() as db:
        sermon = db.scalar(
            select(Sermon).options(selectinload(Sermon.segments)).where(Sermon.id == sermon_id)
        )
        if sermon is None:
            return
        try:
            sermon.status = SermonStatus.TRANSLATING
            sermon.failure_reason = None
            db.commit()
            provider = build_provider()
            sermon.provider_name = provider.name
            sermon.model_name = provider.model_name
            db.commit()

            settings = get_settings()
            timeout = httpx.Timeout(settings.canonical_source_timeout_seconds)
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as http_client:
                canonical_service = CanonicalSourceService(settings, http_client)
                for segment in sermon.segments:
                    mosque_sources = retrieve_sources(
                        db, sermon.mosque_id, segment.arabic_text
                    )
                    canonical = await canonical_service.retrieve(segment.arabic_text)
                    sources = canonical.sources + mosque_sources
                    if not sources:
                        raise RuntimeError(
                            "No usable reference sources were retrieved. Upload a reviewed mosque "
                            "source or include resolvable Qur'an/hadith references."
                        )
                    draft = await provider.translate(
                        segment.arabic_text, sermon.target_language, sources
                    )
                    allowed = {source.chunk_id: source for source in sources}
                    citation_ids = draft.citations + [
                        source.chunk_id for source in canonical.sources
                    ]
                    valid_citation_ids = list(
                        dict.fromkeys(item for item in citation_ids if item in allowed)
                    )
                    issues = list(canonical.issues)
                    issues.extend(f"Uncertain term: {term}" for term in draft.uncertain_terms)
                    if not valid_citation_ids:
                        issues.append("The model did not cite a retrieved trusted-source excerpt")

                    verification = await provider.verify(
                        segment.arabic_text,
                        draft.translation,
                        sermon.target_language,
                        sources,
                    )
                    translated_text = verification.corrected_translation or draft.translation
                    issues.extend(verification.issues)
                    issues.extend(
                        _canonical_wording_issues(
                            translated_text, sermon.target_language, canonical.sources
                        )
                    )
                    segment.translated_text = translated_text
                    segment.citations = [
                        {
                            "chunk_id": item,
                            "source_id": allowed[item].source_id,
                            "title": allowed[item].title,
                            "authority": allowed[item].authority,
                            "excerpt": allowed[item].text[:600],
                            "source_kind": allowed[item].source_kind,
                            "url": allowed[item].url,
                        }
                        for item in valid_citation_ids
                    ]
                    segment.issues = list(dict.fromkeys(issues))
                    segment.verification_status = (
                        VerificationStatus.PASSED
                        if verification.passed and not issues
                        else VerificationStatus.FLAGGED
                    )
                    db.commit()

            sermon.status = SermonStatus.REVIEW_REQUIRED
            db.commit()
        except Exception as exc:
            db.rollback()
            sermon = db.get(Sermon, sermon_id)
            if sermon is not None:
                sermon.status = SermonStatus.FAILED
                sermon.failure_reason = str(exc)[:2000]
                db.commit()


def run_translation_job_sync(sermon_id: str) -> None:
    asyncio.run(run_translation_job(sermon_id))
