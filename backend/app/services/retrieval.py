import math
import re
from collections import Counter
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SourceChunk, TrustedSource

TOKEN_RE = re.compile(r"[\w\u0600-\u06FF]+", re.UNICODE)
ARABIC_DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")


def normalize(value: str) -> list[str]:
    value = ARABIC_DIACRITICS.sub("", value.lower())
    value = value.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي"}))
    return TOKEN_RE.findall(value)


@dataclass(frozen=True)
class RetrievedSource:
    chunk_id: str
    source_id: str
    title: str
    authority: str
    text: str
    score: float
    source_kind: str = "mosque"
    url: str | None = None
    canonical: bool = False
    verbatim_required: bool = False


def retrieve_sources(
    db: Session, mosque_id: str, query: str, limit: int = 5
) -> list[RetrievedSource]:
    rows = db.execute(
        select(SourceChunk, TrustedSource)
        .join(TrustedSource, SourceChunk.source_id == TrustedSource.id)
        .where(TrustedSource.mosque_id == mosque_id)
    ).all()
    if not rows:
        return []

    query_terms = Counter(normalize(query))
    if not query_terms:
        return []
    document_terms = [Counter(normalize(chunk.text)) for chunk, _ in rows]
    doc_count = len(rows)
    frequencies = Counter(
        term for term in query_terms for tokens in document_terms if term in tokens
    )
    scored: list[RetrievedSource] = []
    for (chunk, source), tokens in zip(rows, document_terms, strict=True):
        length_normalizer = 1 + math.log(1 + sum(tokens.values()))
        score = 0.0
        for term, query_frequency in query_terms.items():
            if tokens[term]:
                inverse_doc_frequency = math.log((doc_count + 1) / (frequencies[term] + 1)) + 1
                score += query_frequency * (1 + math.log(tokens[term])) * inverse_doc_frequency
        score /= length_normalizer
        scored.append(
            RetrievedSource(
                chunk_id=chunk.id,
                source_id=source.id,
                title=source.title,
                authority=source.authority,
                text=chunk.text,
                score=score,
            )
        )
    scored.sort(key=lambda item: item.score, reverse=True)
    # Always provide a bounded reference set, even when overlap is weak; the verifier flags it.
    return scored[:limit]
