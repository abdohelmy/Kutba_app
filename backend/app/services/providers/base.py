from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from app.services.retrieval import RetrievedSource


class TranslationDraft(BaseModel):
    translation: str = Field(min_length=1)
    citations: list[str] = Field(default_factory=list)
    uncertain_terms: list[str] = Field(default_factory=list)


class VerificationResult(BaseModel):
    passed: bool
    corrected_translation: str | None = None
    issues: list[str] = Field(default_factory=list)


class TranslationProvider(ABC):
    name: str
    model_name: str

    @abstractmethod
    async def translate(
        self, arabic_text: str, target_language: str, sources: list[RetrievedSource]
    ) -> TranslationDraft: ...

    @abstractmethod
    async def verify(
        self,
        arabic_text: str,
        translation: str,
        target_language: str,
        sources: list[RetrievedSource],
    ) -> VerificationResult: ...
