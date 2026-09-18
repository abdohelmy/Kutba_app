from dataclasses import dataclass


@dataclass(frozen=True)
class SourceOccurrence:
    arabic_text: str
    start: int | None = None
    end: int | None = None


@dataclass(frozen=True)
class RetrievedSource:
    chunk_id: str
    source_id: str
    title: str
    authority: str
    text: str
    score: float
    source_kind: str = "canonical"
    url: str | None = None
    canonical: bool = False
    verbatim_required: bool = False
    arabic_text: str | None = None
    transliteration: str | None = None
    display_reference: str | None = None
    occurrences: tuple[SourceOccurrence, ...] = ()
    minimum_verbatim_words: int = 0
