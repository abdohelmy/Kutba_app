import re

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Sermon
from app.models.entities import GlobalGlossaryTerm
from app.services.glossary import (
    PARENTHETICAL_RE,
    _glossary_hits_in_arabic,
    _normalized_arabic,
    quotation_glossary_spans,
)
from app.services.mosque_glossary import glossary_entries_for_mosque


class GlossaryCandidate(BaseModel):
    segment_id: str
    arabic_term: str
    sentence: str


class GlossaryContribution(BaseModel):
    segment_id: str
    arabic_term: str = Field(min_length=1, max_length=250)
    literal_translation: str = Field(min_length=1, max_length=500)
    meaning: str = Field(min_length=3, max_length=4000)


def global_term_key(term: str) -> str:
    # Unlike the legacy mosque key, do not collapse هدى and هدي.
    return " ".join(_normalized_arabic(term, False))


def missing_glossary_candidates(db: Session, sermon: Sermon) -> list[GlossaryCandidate]:
    catalog = glossary_entries_for_mosque(db, sermon.mosque_id)
    found = []
    seen = set()
    # A definition already awaiting review must not be repeatedly resubmitted.
    submitted = set(
        db.scalars(
            select(GlobalGlossaryTerm.normalized_term).where(
                GlobalGlossaryTerm.approval_status.in_(["PENDING", "APPROVED"])
            )
        )
    )
    for segment in sermon.segments:
        text = segment.translated_text or ""
        protected = quotation_glossary_spans(text, segment.citations)
        for match in PARENTHETICAL_RE.finditer(text):
            term = match.group("arabic").strip()
            key = global_term_key(term)
            if not key or key in seen or key in submitted:
                continue
            if any(match.start() < end and start < match.end() for start, end in protected):
                continue
            # A known word inside a longer expression does not define that expression.
            if any(
                hit.position == 0 and len(hit.form.normalized_words) == len(key.split())
                for hit in _glossary_hits_in_arabic(term, catalog)
            ) or any(key == global_term_key(entry.arabic_term) for entry in catalog):
                continue
            # Only offer terms grounded in the original Arabic, not model inventions.
            source = " " + global_term_key(segment.arabic_text) + " "
            if " " + key + " " not in source:
                continue
            boundaries = list(re.finditer(r"[.!?;]\s+|\n\s*\n", text[: match.start()]))
            start = boundaries[-1].end() if boundaries else 0
            following = re.search(r"[.!?;](?:\s|$)|\n\s*\n", text[match.end() :])
            end = match.end() + following.end() if following else len(text)
            found.append(
                GlossaryCandidate(
                    segment_id=segment.id,
                    arabic_term=term,
                    sentence=text[start:end].strip(),
                )
            )
            seen.add(key)
    return found
