from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from app.services.glossary import GlossaryEntry
from app.services.retrieval import RetrievedSource


class SourceTransliteration(BaseModel):
    source_id: str = Field(min_length=1)
    transliteration: str = Field(min_length=1)


class TranslationDraft(BaseModel):
    translation: str = Field(min_length=1)
    suggested_title: str | None = Field(default=None, max_length=250)
    citations: list[str] = Field(default_factory=list)
    uncertain_terms: list[str] = Field(default_factory=list)
    source_transliterations: list[SourceTransliteration] = Field(default_factory=list)


class VerificationResult(BaseModel):
    passed: bool
    corrected_translation: str | None = None
    issues: list[str] = Field(default_factory=list)
    uncertain_terms: list[str] = Field(default_factory=list)
    source_transliterations: list[SourceTransliteration] = Field(default_factory=list)


class SunnahWebCandidate(BaseModel):
    collection: str = Field(
        min_length=1,
        description="Sunnah.com collection slug, for example muslim, bukhari, or tirmidhi",
    )
    hadith_number: str = Field(
        min_length=1,
        description="Hadith number shown on the matching Sunnah.com page",
    )
    title: str = Field(min_length=1)
    arabic_text: str = Field(min_length=1)
    english_text: str = Field(min_length=1)
    url: str = Field(min_length=1, description="HTTPS Sunnah.com page containing the match")
    grade: str | None = None


class SunnahWebSearchResult(BaseModel):
    candidates: list[SunnahWebCandidate] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


class TranslationProvider(ABC):
    name: str
    model_name: str

    @abstractmethod
    async def translate(
        self,
        arabic_text: str,
        target_language: str,
        sources: list[RetrievedSource],
        glossary_entries: list[GlossaryEntry] | None = None,
    ) -> TranslationDraft: ...

    @abstractmethod
    async def verify(
        self,
        arabic_text: str,
        translation: str,
        target_language: str,
        sources: list[RetrievedSource],
        source_transliterations: list[SourceTransliteration] | None = None,
        glossary_entries: list[GlossaryEntry] | None = None,
    ) -> VerificationResult: ...

    async def search_sunnah(self, arabic_passage: str) -> SunnahWebSearchResult:
        """Optional hosted-search fallback; local providers remain fully usable without it."""
        return SunnahWebSearchResult(
            issues=[
                "Sunnah.com web-search fallback is unavailable for the selected translation "
                "provider"
            ]
        )
