import json

from openai import AsyncOpenAI

from app.services.providers.base import TranslationDraft, TranslationProvider, VerificationResult
from app.services.retrieval import RetrievedSource


def _source_context(sources: list[RetrievedSource]) -> str:
    return "\n\n".join(
        (
            f"[S:{source.chunk_id}] {source.title} — {source.authority}"
            f"{' — CANONICAL WORDING' if source.canonical else ''}"
            f"{f' — {source.url}' if source.url else ''}\n{source.text}"
        )
        for source in sources
    )


TRANSLATION_INSTRUCTIONS = """You are a careful Arabic Islamic-sermon translator.
Translate only the supplied Arabic segment into the requested target language.

Success criteria:
- Preserve every claim, qualification, Qur'anic quotation, hadith, name, and legal term.
- Prefer established wording in the trusted reference excerpts when they support the Arabic.
- For an English Qur'an or hadith quotation backed by a CANONICAL WORDING excerpt, copy the
  applicable canonical English wording exactly. Do not paraphrase, smooth, or re-translate it.
- Cite only source IDs exactly as [S:<id>] from the supplied excerpts.
- Do not add commentary, rulings, or facts that are absent from the Arabic.
- Put genuinely ambiguous religious terms in uncertain_terms rather than guessing.
- If a trusted excerpt conflicts with the Arabic segment, translate the Arabic and flag the term.

Return the structured result only. Citations are evidence for reviewer inspection, not proof of
infallibility. A human reviewer will approve or amend the result before publication."""

VERIFICATION_INSTRUCTIONS = """Act as an independent bilingual Islamic-content verifier.
Compare the Arabic segment word-for-word and claim-for-claim with the proposed translation and
the trusted excerpts. Flag omissions, additions, polarity changes, number/name errors, mistranslated
technical terms, unsupported source wording, and altered Qur'an or hadith quotations. Set passed to
false for any material problem and provide a complete corrected_translation. Never claim certainty
that the evidence does not support. When the target is English, canonical Qur'an and hadith wording
must be preserved exactly wherever the corresponding Arabic quotation is present. Return the
structured result only."""


class OpenAIResponsesProvider(TranslationProvider):
    """Responses adapter whose model boundary is text-only; uploaded files never enter it."""

    name = "openai"

    def __init__(
        self,
        api_key: str,
        model: str,
        verifier_model: str | None = None,
        reasoning_effort: str = "high",
    ) -> None:
        self.translation_model = model
        self.verifier_model = verifier_model or model
        self.model_name = f"{self.translation_model}; verifier={self.verifier_model}"
        self.reasoning_effort = reasoning_effort
        self.client = AsyncOpenAI(api_key=api_key)

    async def translate(
        self, arabic_text: str, target_language: str, sources: list[RetrievedSource]
    ) -> TranslationDraft:
        response = await self.client.responses.parse(
            model=self.translation_model,
            reasoning={"effort": self.reasoning_effort},
            instructions=TRANSLATION_INSTRUCTIONS,
            input=(
                f"TARGET LANGUAGE: {target_language}\n\n"
                f"ARABIC SEGMENT:\n{arabic_text}\n\n"
                f"TRUSTED EXCERPTS:\n{_source_context(sources)}"
            ),
            store=False,
            text_format=TranslationDraft,
        )
        if response.output_parsed is None:
            raise RuntimeError("The translation model did not return a structured result")
        return response.output_parsed

    async def verify(
        self,
        arabic_text: str,
        translation: str,
        target_language: str,
        sources: list[RetrievedSource],
    ) -> VerificationResult:
        response = await self.client.responses.parse(
            model=self.verifier_model,
            reasoning={"effort": self.reasoning_effort},
            instructions=VERIFICATION_INSTRUCTIONS,
            input=(
                f"TARGET LANGUAGE: {target_language}\n\n"
                f"ARABIC SEGMENT:\n{arabic_text}\n\n"
                f"PROPOSED TRANSLATION:\n{translation}\n\n"
                f"TRUSTED EXCERPTS:\n{_source_context(sources)}"
            ),
            store=False,
            text_format=VerificationResult,
        )
        if response.output_parsed is None:
            raise RuntimeError("The verification model did not return a structured result")
        return response.output_parsed


class OpenAICompatibleProvider(TranslationProvider):
    """Text-only adapter for vLLM, Ollama, and similar OpenAI-compatible servers."""

    name = "openai_compatible"

    def __init__(
        self,
        base_url: str,
        model: str,
        verifier_model: str | None = None,
        api_key: str = "local",
    ) -> None:
        self.translation_model = model
        self.verifier_model = verifier_model or model
        self.model_name = f"{self.translation_model}; verifier={self.verifier_model}"
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def _json(self, model: str, system: str, user: str) -> dict:
        response = await self.client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={"type": "json_object"},
            temperature=0,
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("The local model returned an empty response")
        return json.loads(content)

    async def translate(
        self, arabic_text: str, target_language: str, sources: list[RetrievedSource]
    ) -> TranslationDraft:
        schema = json.dumps(TranslationDraft.model_json_schema())
        data = await self._json(
            self.translation_model,
            TRANSLATION_INSTRUCTIONS,
            f"JSON SCHEMA: {schema}\nTARGET: {target_language}\nARABIC: {arabic_text}\n"
            f"SOURCES:\n{_source_context(sources)}",
        )
        return TranslationDraft.model_validate(data)

    async def verify(
        self,
        arabic_text: str,
        translation: str,
        target_language: str,
        sources: list[RetrievedSource],
    ) -> VerificationResult:
        schema = json.dumps(VerificationResult.model_json_schema())
        data = await self._json(
            self.verifier_model,
            VERIFICATION_INSTRUCTIONS,
            f"JSON SCHEMA: {schema}\nTARGET: {target_language}\nARABIC: {arabic_text}\n"
            f"TRANSLATION: {translation}\nSOURCES:\n{_source_context(sources)}",
        )
        return VerificationResult.model_validate(data)


class MockProvider(TranslationProvider):
    name = "mock"
    model_name = "deterministic-test-provider"

    async def translate(
        self, arabic_text: str, target_language: str, sources: list[RetrievedSource]
    ) -> TranslationDraft:
        return TranslationDraft(
            translation=f"[{target_language}] {arabic_text}",
            citations=[sources[0].chunk_id] if sources else [],
        )

    async def verify(
        self,
        arabic_text: str,
        translation: str,
        target_language: str,
        sources: list[RetrievedSource],
    ) -> VerificationResult:
        return VerificationResult(passed=True)
