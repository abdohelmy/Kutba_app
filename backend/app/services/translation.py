import asyncio
import re
from dataclasses import replace
from urllib.parse import unquote, urlparse

import httpx
from openai import AuthenticationError, BadRequestError, RateLimitError
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import Sermon, SermonStatus, VerificationStatus
from app.services.canonical_sources import (
    CanonicalRetrieval,
    CanonicalSourceService,
    PassageCandidate,
    arabic_passage_is_contained,
    arabic_word_overlap,
    deduplicate_embedded_quran_sources,
    find_arabic_occurrences,
    hadith_passages_match,
    hadith_search_excerpt,
    hadith_web_search_candidates,
    normalize_arabic_words,
)
from app.services.glossary import ensure_glossary_parentheticals, glossary_entries_in_arabic
from app.services.mosque_glossary import glossary_entries_for_mosque
from app.services.providers import build_provider
from app.services.providers.base import (
    SourceTransliteration,
    SunnahWebCandidate,
    TranslationProvider,
)
from app.services.retrieval import RetrievedSource, SourceOccurrence
from app.services.sermon_titles import infer_translated_title

SUNNAH_HADITH_NUMBER_RE = re.compile(r"^[0-9]+[a-z]?$", re.IGNORECASE)
PREFERRED_SUNNAH_COLLECTIONS = {"muslim": 0, "bukhari": 1, "tirmidhi": 2}
SUNNAH_COLLECTION_TITLES = {
    "bukhari": "Sahih al-Bukhari",
    "muslim": "Sahih Muslim",
    "nasai": "Sunan an-Nasa'i",
    "abudawud": "Sunan Abi Dawud",
    "tirmidhi": "Jami` at-Tirmidhi",
    "ibnmajah": "Sunan Ibn Majah",
    "malik": "Muwatta Malik",
    "riyadussalihin": "Riyad as-Salihin",
    "nawawi40": "Forty Hadith of an-Nawawi",
    "qudsi40": "Forty Hadith Qudsi",
}
SUNNAH_COLLECTION_ALIASES = {
    "bukhari": "bukhari",
    "sahihalbukhari": "bukhari",
    "muslim": "muslim",
    "sahihmuslim": "muslim",
    "nasai": "nasai",
    "sunanannasai": "nasai",
    "sunananasai": "nasai",
    "abudawud": "abudawud",
    "abidawud": "abudawud",
    "sunanabidawud": "abudawud",
    "sunanabudawud": "abudawud",
    "tirmidhi": "tirmidhi",
    "jamiattirmidhi": "tirmidhi",
    "jamiatirmidhi": "tirmidhi",
    "ibnmajah": "ibnmajah",
    "sunanibnmajah": "ibnmajah",
    "malik": "malik",
    "muwattamalik": "malik",
    "riyadussalihin": "riyadussalihin",
    "riyadassalihin": "riyadussalihin",
    "nawawi40": "nawawi40",
    "fortyhadithofannawawi": "nawawi40",
    "qudsi40": "qudsi40",
    "fortyhadithqudsi": "qudsi40",
}
ARABIC_TERM_RE = re.compile(r"[\u0600-\u06ff]+(?:\s+[\u0600-\u06ff]+)*")
ENGLISH_SOURCE_TOKEN_RE = re.compile(r"[\w]+(?:[’'][\w]+)*", re.UNICODE)
SOURCE_MARKER_RE = re.compile(r"\s*\[S:(?P<source_id>[^\]\r\n]+)\]")
SOURCE_MARKER_FULL_RE = re.compile(r"^\[S:(?P<source_id>[^\]\r\n]+)\]$")


def _failure_message(exc: Exception) -> str:
    if isinstance(exc, AuthenticationError):
        return "OpenAI rejected the API key. Replace the server-side key and try again."
    if isinstance(exc, RateLimitError):
        if (
            getattr(exc, "code", None) == "credit_balance_exhausted"
            or "no credits" in str(exc).lower()
        ):
            return (
                "The OpenAI project has no API credits remaining. Add billing credits, then retry "
                "the translation."
            )
        return "OpenAI rate-limited the translation. Wait briefly and try again."
    if isinstance(exc, BadRequestError):
        return f"OpenAI rejected the translation configuration: {exc.message}"
    return str(exc)


def _canonical_wording_issues(
    translated_text: str, target_language: str, sources: list[RetrievedSource]
) -> list[str]:
    if target_language.lower() not in {"en", "eng", "english"}:
        return []
    normalized_translation = " ".join(translated_text.split())
    issues: list[str] = []
    for source in sources:
        spans = _canonical_translation_spans(translated_text, source)
        if source.verbatim_required and " ".join(source.text.split()) not in normalized_translation:
            issues.append(
                f"Canonical {source.source_kind} wording from {source.authority} was not copied "
                "verbatim"
            )
        elif source.minimum_verbatim_words and not spans:
            issues.append(
                f"The partial {source.source_kind} quotation did not preserve enough consecutive "
                f"canonical words from {source.authority}"
            )
        expected_occurrences = len(source.occurrences)
        if expected_occurrences > 1 and len(spans) < expected_occurrences:
            issues.append(
                f"Canonical {source.source_kind} wording appears {expected_occurrences} times in "
                f"the Arabic but only {len(spans)} matching English occurrence(s) were found"
            )
    return issues


def _canonical_translation_spans(
    translated_text: str, source: RetrievedSource
) -> list[tuple[int, int]]:
    required_words = (
        len(ENGLISH_SOURCE_TOKEN_RE.findall(source.text))
        if source.verbatim_required
        else source.minimum_verbatim_words
    )
    if required_words <= 0:
        return []
    translated_tokens = [
        (match.group(0).casefold(), match.start(), match.end())
        for match in ENGLISH_SOURCE_TOKEN_RE.finditer(translated_text)
    ]
    source_tokens = [
        match.group(0).casefold() for match in ENGLISH_SOURCE_TOKEN_RE.finditer(source.text)
    ]
    candidates: list[tuple[int, int, int]] = []
    for translated_index, (translated_word, _start, _end) in enumerate(translated_tokens):
        for source_index, source_word in enumerate(source_tokens):
            if translated_word != source_word:
                continue
            if (
                translated_index > 0
                and source_index > 0
                and translated_tokens[translated_index - 1][0] == source_tokens[source_index - 1]
            ):
                continue
            run = 0
            while (
                translated_index + run < len(translated_tokens)
                and source_index + run < len(source_tokens)
                and translated_tokens[translated_index + run][0]
                == source_tokens[source_index + run]
            ):
                run += 1
            if run >= required_words:
                candidates.append(
                    (
                        translated_tokens[translated_index][1],
                        translated_tokens[translated_index + run - 1][2],
                        run,
                    )
                )
    selected: list[tuple[int, int, int]] = []
    for candidate in sorted(candidates, key=lambda item: (-item[2], item[0])):
        if any(candidate[0] < item[1] and item[0] < candidate[1] for item in selected):
            continue
        selected.append(candidate)
    return [(start, end) for start, end, _run in sorted(selected)]


def _citation_payloads(
    source: RetrievedSource,
    translated_text: str,
    transliteration: str | None,
) -> list[dict[str, object]]:
    spans = _canonical_translation_spans(translated_text, source)
    expected = max(1, len(source.occurrences))
    selected_spans: list[tuple[int, int] | None] = list(spans[:expected]) or [None]
    payloads: list[dict[str, object]] = []
    for index, span in enumerate(selected_spans):
        occurrence = source.occurrences[index] if index < len(source.occurrences) else None
        payloads.append(
            {
                "chunk_id": source.chunk_id,
                "source_id": source.source_id,
                "title": source.title,
                "authority": source.authority,
                "excerpt": (translated_text[span[0] : span[1]] if span else source.text[:600]),
                "arabic_excerpt": source.arabic_text[:1200] if source.arabic_text else None,
                "transliteration": source.transliteration or transliteration,
                "display_reference": source.display_reference,
                "source_kind": source.source_kind,
                "url": source.url,
                "translation_start": span[0] if span else None,
                "translation_end": span[1] if span else None,
                "arabic_start": occurrence.start if occurrence else None,
                "arabic_end": occurrence.end if occurrence else None,
            }
        )
    return payloads


def _normalized_transliterations(
    items: list[SourceTransliteration], allowed: dict[str, RetrievedSource]
) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for item in items:
        value = " ".join(item.transliteration.split())
        if (
            item.source_id in allowed
            and value
            and len(value) <= 4000
            and ARABIC_TERM_RE.search(value) is None
        ):
            normalized[item.source_id] = value
    return normalized


def _ambiguous_term_issues(translated_text: str, uncertain_terms: list[str]) -> list[str]:
    issues: list[str] = []
    for uncertain_term in uncertain_terms:
        for arabic_term in ARABIC_TERM_RE.findall(uncertain_term):
            if f"({arabic_term})" not in translated_text:
                issues.append(
                    f"Ambiguous term {arabic_term} must appear in parentheses immediately after "
                    "its English wording"
                )
    return issues


def _normalize_source_id(value: str) -> str:
    value = value.strip()
    marker = SOURCE_MARKER_FULL_RE.fullmatch(value)
    return marker.group("source_id").strip() if marker else value


def _sanitize_translation_source_markers(
    translated_text: str, allowed: dict[str, RetrievedSource]
) -> tuple[str, list[str]]:
    unknown_ids: list[str] = []

    def replace_marker(match: re.Match[str]) -> str:
        source_id = match.group("source_id").strip()
        if source_id not in allowed:
            unknown_ids.append(source_id)
        return ""

    cleaned = SOURCE_MARKER_RE.sub(replace_marker, translated_text)
    cleaned = re.sub(r"[ \t]+([,.;:!?])", r"\1", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()
    issues = [
        f"The model inserted an unknown source marker ({source_id}); it was removed"
        for source_id in dict.fromkeys(unknown_ids)
    ]
    return cleaned, issues


def _normalize_sunnah_collection(value: str) -> str | None:
    compact = re.sub(r"[^a-z0-9]+", "", value.lower())
    return SUNNAH_COLLECTION_ALIASES.get(compact)


def _sunnah_url_collection(path: str) -> str | None:
    first_component = unquote(path).strip("/").split("/", maxsplit=1)[0]
    first_component = first_component.split(":", maxsplit=1)[0]
    return _normalize_sunnah_collection(first_component)


def _validate_sunnah_source(
    candidate: SunnahWebCandidate,
    arabic_passage: PassageCandidate | str,
    sermon_text: str,
) -> tuple[RetrievedSource | None, str | None]:
    passage_text = (
        arabic_passage.text if isinstance(arabic_passage, PassageCandidate) else arabic_passage
    )
    parsed = urlparse(candidate.url.strip())
    if parsed.scheme != "https" or parsed.hostname not in {"sunnah.com", "www.sunnah.com"}:
        return None, "the result was not an HTTPS Sunnah.com page"
    collection = _normalize_sunnah_collection(candidate.collection)
    if collection is None:
        return None, f"the collection name '{candidate.collection}' was not recognized"
    url_collection = _sunnah_url_collection(parsed.path)
    if url_collection is not None and url_collection != collection:
        return None, "the collection name conflicted with the Sunnah.com page"
    candidate_number = candidate.hadith_number.strip().lower()
    if not SUNNAH_HADITH_NUMBER_RE.fullmatch(candidate_number):
        return None, "the Hadith number was not usable"
    overlap = arabic_word_overlap(passage_text, candidate.arabic_text)
    if overlap < 0.70:
        return None, f"Arabic overlap was {overlap:.0%}, below the required 70%"
    english = " ".join(candidate.english_text.split())
    if not english:
        return None, "the Sunnah.com result had no English translation"
    grade = " ".join(candidate.grade.split()) if candidate.grade else ""
    title = " ".join(candidate.title.split())
    if grade and grade.lower() not in title.lower():
        title = f"{title} — {grade}"
    occurrences = ()
    if isinstance(arabic_passage, PassageCandidate):
        if arabic_passage.start is not None and arabic_passage.end is not None:
            occurrences = (
                SourceOccurrence(
                    sermon_text[arabic_passage.start : arabic_passage.end],
                    arabic_passage.start,
                    arabic_passage.end,
                ),
            )
    if not occurrences:
        occurrences = find_arabic_occurrences(sermon_text, passage_text)
    verbatim_required = arabic_passage_is_contained(sermon_text, candidate.arabic_text)
    return RetrievedSource(
        chunk_id=f"canonical:sunnah:{collection}:{candidate_number}",
        source_id=f"sunnah.com:{collection}:{candidate_number}",
        title=title,
        authority="Sunnah.com",
        text=english,
        score=10_000,
        source_kind="hadith",
        url=f"https://sunnah.com/{collection}:{candidate_number}",
        canonical=True,
        verbatim_required=verbatim_required,
        arabic_text=" ".join(candidate.arabic_text.split()),
        display_reference=f"{SUNNAH_COLLECTION_TITLES[collection]} {candidate_number}",
        occurrences=occurrences,
        minimum_verbatim_words=(
            0
            if verbatim_required
            else max(3, min(8, round(len(re.findall(r"\S+", passage_text)) * 0.75)))
        ),
    ), None


def _validated_sunnah_source(
    candidate: SunnahWebCandidate,
    arabic_passage: PassageCandidate | str,
    sermon_text: str,
) -> RetrievedSource | None:
    source, _reason = _validate_sunnah_source(candidate, arabic_passage, sermon_text)
    return source


async def _sunnah_web_fallback(
    provider: TranslationProvider,
    arabic_text: str,
    existing_sources: list[RetrievedSource],
    max_concurrency: int = 3,
) -> tuple[list[RetrievedSource], list[str]]:
    passages = hadith_web_search_candidates(arabic_text)
    if not passages:
        return [], []

    grouped_passages: dict[tuple[str, ...], list[PassageCandidate]] = {}
    for passage in passages:
        key = normalize_arabic_words(passage.text)
        grouped_passages.setdefault(key, []).append(passage)
    semaphore = asyncio.Semaphore(max(1, min(max_concurrency, 8)))

    async def search_passage(
        passage_group: list[PassageCandidate],
    ) -> tuple[list[RetrievedSource], list[str]]:
        passage = passage_group[0]
        already_sourced = any(
            source.source_kind == "hadith"
            and source.arabic_text
            and hadith_passages_match(passage.text, source.arabic_text)
            for source in existing_sources
        )
        if already_sourced:
            return [], []
        try:
            async with semaphore:
                result = await provider.search_sunnah(hadith_search_excerpt(passage.text))
        except Exception as exc:
            excerpt = " ".join(passage.text.split()[:12])
            return [], [
                f"Sunnah.com web search failed for '{excerpt}': {exc}. "
                "Verify whether the passage is a hadith before approval."
            ]
        validated: list[tuple[float, RetrievedSource]] = []
        rejection_reasons: list[str] = []
        for candidate in result.candidates[:3]:
            source, rejection_reason = _validate_sunnah_source(
                candidate,
                passage,
                arabic_text,
            )
            if source is not None:
                validated.append((arabic_word_overlap(passage.text, candidate.arabic_text), source))
            elif rejection_reason:
                rejection_reasons.append(rejection_reason)
        ranked_sources = sorted(
            validated,
            key=lambda item: (
                -item[0],
                PREFERRED_SUNNAH_COLLECTIONS.get(item[1].source_id.split(":", maxsplit=2)[1], 99),
            ),
        )
        sources: list[RetrievedSource] = []
        if ranked_sources:
            best = ranked_sources[0][1]
            occurrences = tuple(
                SourceOccurrence(arabic_text[item.start : item.end], item.start, item.end)
                for item in passage_group
                if item.start is not None and item.end is not None
            )
            sources = [replace(best, occurrences=occurrences or best.occurrences)]
        issues = list(result.issues)
        if result.candidates and not sources:
            excerpt = " ".join(passage.text.split()[:12])
            reason_summary = "; ".join(dict.fromkeys(rejection_reasons))
            issues.append(
                f"Sunnah.com candidates for '{excerpt}' were rejected"
                f"{f': {reason_summary}' if reason_summary else ''}; "
                "verify whether it is a hadith before approval."
            )
        return sources, issues

    results = await asyncio.gather(*(search_passage(group) for group in grouped_passages.values()))
    sources_by_id: dict[str, RetrievedSource] = {}
    for passage_sources, _ in results:
        for source in passage_sources:
            existing = sources_by_id.get(source.chunk_id)
            if existing is None:
                sources_by_id[source.chunk_id] = source
                continue
            merged_occurrences = tuple(
                {
                    (item.start, item.end, item.arabic_text): item
                    for item in (*existing.occurrences, *source.occurrences)
                }.values()
            )
            sources_by_id[source.chunk_id] = replace(
                existing,
                occurrences=merged_occurrences,
                verbatim_required=existing.verbatim_required or source.verbatim_required,
                minimum_verbatim_words=max(
                    existing.minimum_verbatim_words, source.minimum_verbatim_words
                ),
            )
    issues = [issue for _, passage_issues in results for issue in passage_issues]
    return list(sources_by_id.values()), list(dict.fromkeys(issues))


async def _canonical_sources_for_segment(
    provider: TranslationProvider,
    canonical_service: CanonicalSourceService,
    arabic_text: str,
    sunnah_web_search_enabled: bool,
    sunnah_web_search_concurrency: int = 3,
) -> CanonicalRetrieval:
    """Classify bounded passages as hadith first, Qur'an second, or ordinary prose."""
    hadith = await canonical_service.retrieve_hadith(arabic_text)
    web_sources: list[RetrievedSource] = []
    web_issues: list[str] = []
    if sunnah_web_search_enabled:
        web_sources, web_issues = await _sunnah_web_fallback(
            provider,
            arabic_text,
            hadith.sources,
            sunnah_web_search_concurrency,
        )
    quran = await canonical_service.retrieve_quran(arabic_text)
    sources = deduplicate_embedded_quran_sources(hadith.sources + web_sources + quran.sources)
    sources.sort(key=lambda source: (source.source_kind, source.chunk_id))
    hadith_issues = hadith.issues
    if sunnah_web_search_enabled:
        hadith_issues = [
            issue
            for issue in hadith_issues
            if not issue.startswith("Possible hadith quotation or bounded Arabic quotation")
        ]
    issues = list(dict.fromkeys(hadith_issues + web_issues + quran.issues))
    return CanonicalRetrieval(sources, issues)


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
            glossary_catalog = glossary_entries_for_mosque(db, sermon.mosque_id)
            timeout = httpx.Timeout(settings.canonical_source_timeout_seconds)
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as http_client:
                canonical_service = CanonicalSourceService(settings, http_client)
                suggested_titles: list[str] = []
                for segment in sermon.segments:
                    # Each completed section is committed atomically; a retry resumes the rest.
                    if segment.translated_text:
                        continue
                    glossary_entries = glossary_entries_in_arabic(
                        segment.arabic_text,
                        glossary_catalog,
                    )
                    canonical = await _canonical_sources_for_segment(
                        provider,
                        canonical_service,
                        segment.arabic_text,
                        settings.sunnah_web_search_fallback_enabled,
                        settings.sunnah_web_search_concurrency,
                    )
                    canonical_sources = canonical.sources
                    sources = canonical_sources
                    draft = await provider.translate(
                        segment.arabic_text,
                        sermon.target_language,
                        sources,
                        glossary_entries=glossary_entries,
                    )
                    if segment.ordinal == 0 and draft.suggested_title:
                        suggested_titles.append(draft.suggested_title)
                    allowed = {source.chunk_id: source for source in sources}
                    citation_ids = [_normalize_source_id(item) for item in draft.citations] + [
                        source.chunk_id for source in canonical_sources
                    ]
                    valid_citation_ids = list(
                        dict.fromkeys(item for item in citation_ids if item in allowed)
                    )
                    issues = list(canonical.issues)
                    if not valid_citation_ids:
                        issues.append(
                            "No canonical source supports this prose segment; "
                            "review the translation directly against the Arabic."
                        )

                    draft_translation, marker_issues = _sanitize_translation_source_markers(
                        draft.translation, allowed
                    )
                    issues.extend(marker_issues)

                    verification = await provider.verify(
                        segment.arabic_text,
                        draft_translation,
                        sermon.target_language,
                        sources,
                        draft.source_transliterations,
                        glossary_entries=glossary_entries,
                    )
                    translated_text = verification.corrected_translation or draft_translation
                    translated_text, marker_issues = _sanitize_translation_source_markers(
                        translated_text, allowed
                    )
                    issues.extend(marker_issues)
                    issues.extend(verification.issues)
                    verified_uncertain_terms = verification.uncertain_terms
                    translated_text, glossary_issues = ensure_glossary_parentheticals(
                        segment.arabic_text,
                        translated_text,
                        verified_uncertain_terms,
                        glossary_catalog,
                    )
                    issues.extend(glossary_issues)
                    issues.extend(f"Uncertain term: {term}" for term in verified_uncertain_terms)
                    issues.extend(_ambiguous_term_issues(translated_text, verified_uncertain_terms))
                    issues.extend(
                        _canonical_wording_issues(
                            translated_text, sermon.target_language, canonical_sources
                        )
                    )
                    model_transliterations = _normalized_transliterations(
                        verification.source_transliterations or draft.source_transliterations,
                        allowed,
                    )
                    missing_transliterations = [
                        source
                        for source in canonical_sources
                        if source.chunk_id in valid_citation_ids
                        and source.arabic_text
                        and not source.transliteration
                        and source.chunk_id not in model_transliterations
                    ]
                    issues.extend(
                        f"No Latin transliteration was generated for {source.title}; "
                        "add or verify it before approval."
                        for source in missing_transliterations
                    )
                    segment.translated_text = translated_text
                    segment.citations = [
                        citation
                        for item in valid_citation_ids
                        for citation in _citation_payloads(
                            allowed[item],
                            translated_text,
                            model_transliterations.get(item),
                        )
                    ]
                    segment.issues = list(dict.fromkeys(issues))
                    segment.verification_status = (
                        VerificationStatus.PASSED
                        if verification.passed and not issues
                        else VerificationStatus.FLAGGED
                    )
                    db.commit()

            if sermon.title_is_inferred:
                sermon.title = infer_translated_title(
                    suggested_titles
                    + [segment.translated_text or "" for segment in sermon.segments],
                    sermon.title,
                    sermon.khutba_date,
                )
            sermon.status = SermonStatus.REVIEW_REQUIRED
            db.commit()
        except Exception as exc:
            db.rollback()
            sermon = db.get(Sermon, sermon_id)
            if sermon is not None:
                sermon.status = SermonStatus.FAILED
                sermon.failure_reason = _failure_message(exc)[:2000]
                db.commit()


def run_translation_job_sync(sermon_id: str) -> None:
    asyncio.run(run_translation_job(sermon_id))
