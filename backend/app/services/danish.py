"""Localize reviewed content without re-running retrieval or reusing English offsets."""

import hashlib
import json
import re

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.session import SessionLocal
from app.models import Sermon, SermonStatus, VerificationStatus
from app.services.glossary import PARENTHETICAL_RE
from app.services.providers.factory import build_provider
from app.services.providers.localization import DanishDraft


def english_revision(sermon: Sermon) -> str:
    data = [sermon.title, sermon.arabic_text, [
        [s.ordinal, s.arabic_text, s.translated_text, s.citations] for s in sermon.segments
    ]]
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def english_is_current(sermon: Sermon, db: Session) -> bool:
    if not sermon.english_sermon_id:
        return True
    parent = db.get(Sermon, sermon.english_sermon_id)
    return bool(parent and parent.status == SermonStatus.PUBLISHED
                and all(s.verification_status == VerificationStatus.HUMAN_APPROVED
                        for s in parent.segments)
                and english_revision(parent) == sermon.english_revision)


def translation_parts(text: str, citations: list[dict]) -> list[dict]:
    """Split only at known quotation boundaries, never at arbitrary sentences."""
    boundaries = {0, len(text)}
    for citation in citations:
        start, end = citation.get("translation_start"), citation.get("translation_end")
        if (not isinstance(start, int) or not isinstance(end, int)
                or not 0 <= start < end <= len(text)
                or not citation.get("anchor_valid", True)
                or text[start:end] != citation.get("excerpt")):
            raise ValueError("An English citation needs review before creating Danish")
        boundaries.update((start, end))
    ordered = sorted(boundaries)
    return [{"id": i, "text": text[a:b], "start": a, "end": b}
            for i, (a, b) in enumerate(zip(ordered, ordered[1:], strict=False))]


def assemble_danish(parts: list[dict], citations: list[dict], terms: list[dict],
                    draft: DanishDraft) -> tuple[str, list[dict], list[dict]]:
    if [p.id for p in draft.parts] != [p["id"] for p in parts]:
        raise ValueError("Danish translation omitted or reordered a passage")
    if sorted(t.id for t in draft.terms) != list(range(len(terms))):
        raise ValueError("Danish translation omitted or duplicated a glossary definition")
    text = ""
    boundaries = {}
    def notes(value):
        return [m.group("arabic") for m in PARENTHETICAL_RE.finditer(value)]
    for original, localized in zip(parts, draft.parts, strict=True):
        if notes(original["text"]) != notes(localized.text):
            raise ValueError("Danish translation changed an Arabic glossary note")
        boundaries[original["start"]] = len(text)
        # The model owns words, not the whitespace joining adjacent source parts.
        leading = re.match(r"\s*", original["text"]).group()
        trailing = re.search(r"\s*$", original["text"]).group()
        text += (leading + localized.text.strip() + trailing
                 if original["text"].strip() else original["text"])
        boundaries[original["end"]] = len(text)
    localized_citations = []
    for citation in citations:
        item = dict(citation)
        start, end = boundaries[item["translation_start"]], boundaries[item["translation_end"]]
        item.update(translation_start=start, translation_end=end, excerpt=text[start:end],
                    anchor_valid=True)
        localized_citations.append(item)
    by_id = {t.id: t for t in draft.terms}
    localized_terms = [dict(term, localized_phrase=by_id[i].phrase,
                            meaning=by_id[i].meaning, alternative_context_meanings="")
                       for i, term in enumerate(terms)]
    return text, localized_citations, localized_terms


async def run_danish_job(sermon_id: str) -> None:
    from app.api.routes.reader import _reader_sermon_response
    from app.services.translation import _failure_message

    with SessionLocal() as db:
        sermon = db.scalar(select(Sermon).options(selectinload(Sermon.segments))
                           .where(Sermon.id == sermon_id))
        if sermon is None:
            return
        try:
            if not english_is_current(sermon, db):
                raise ValueError("English has changed or is not published; create Danish again")
            parent = db.get(Sermon, sermon.english_sermon_id)
            source = _reader_sermon_response(parent, db)
            provider = build_provider()
            sermon.provider_name, sermon.model_name = provider.name, provider.model_name
            for segment, english in zip(sermon.segments, source.segments, strict=True):
                if segment.translated_text:
                    continue
                citations = [c.model_dump() for c in english.citations]
                parts = translation_parts(english.translated_text, citations)
                terms = [t.model_dump() for t in english.glossary_terms]
                for term in terms:
                    occurrences = [m for m in PARENTHETICAL_RE.finditer(english.translated_text)
                                   if m.group("arabic").strip() == term["arabic_term"]]
                    term["arabic_occurrence"] = next(
                        (i for i, m in enumerate(occurrences)
                         if m.start() <= term["translation_start"] < m.end()), 0)
                draft = await provider.localize_danish({
                    "title": parent.title, "arabic_context": segment.arabic_text,
                    "parts": parts, "sources": citations,
                    "terms": [dict(t, id=i) for i, t in enumerate(terms)],
                })
                text, refs, glossary = assemble_danish(parts, citations, terms, draft)
                segment.translated_text, segment.citations = text, refs
                segment.localized_glossary = glossary
                segment.verification_status = VerificationStatus.PENDING
                segment.issues = ["Review Danish wording and definitions against approved English. "
                                  "Sources authenticate Arabic/English, not Danish wording."]
                if segment.ordinal == 0:
                    sermon.title = draft.title
                db.commit()
            db.expire_all()
            if not english_is_current(sermon, db):
                raise ValueError("English changed during translation; create Danish again")
            sermon.status = SermonStatus.REVIEW_REQUIRED
            sermon.failure_reason = None
            db.commit()
        except Exception as exc:
            db.rollback()
            sermon = db.get(Sermon, sermon_id)
            if sermon is not None:
                sermon.status = SermonStatus.FAILED
                sermon.failure_reason = _failure_message(exc)
                db.commit()
