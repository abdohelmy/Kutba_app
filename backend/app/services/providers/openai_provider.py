import json

from openai import AsyncOpenAI

from app.services.glossary import GlossaryEntry
from app.services.providers.base import (
    SourceTransliteration,
    SunnahWebSearchResult,
    TranslationDraft,
    TranslationProvider,
    VerificationResult,
)
from app.services.retrieval import RetrievedSource


def _source_context(sources: list[RetrievedSource]) -> str:
    blocks: list[str] = []
    for source in sources:
        lines = [
            f"SOURCE ID: {source.chunk_id}\n{source.title} — {source.authority}"
            f"{' — CANONICAL WORDING' if source.canonical else ''}"
            f"{f' — {source.url}' if source.url else ''}",
            f"CANONICAL ENGLISH: {source.text}",
        ]
        if source.minimum_verbatim_words:
            lines.append(
                "PARTIAL QUOTATION REQUIREMENT: copy the applicable run of at least "
                f"{source.minimum_verbatim_words} consecutive words from CANONICAL ENGLISH "
                "exactly; do not retranslate that Arabic excerpt."
            )
        if source.arabic_text:
            lines.append(f"ARABIC SOURCE: {source.arabic_text}")
        if source.transliteration:
            lines.append(f"CANONICAL TRANSLITERATION: {source.transliteration}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _glossary_context(entries: list[GlossaryEntry] | None) -> str:
    if not entries:
        return "No glossary candidate occurs in this segment."
    blocks: list[str] = []
    for entry in entries:
        variations = [
            f"- {form.arabic_term}"
            f"{f' ({form.grammatical_label})' if form.grammatical_label else ''}"
            f": {form.translation or 'No concise rendering supplied'}"
            for form in entry.forms[1:]
        ]
        blocks.append(
            f"ARABIC TERM: {entry.arabic_term}\n"
            f"CONTEXTUAL MEANING: {entry.meaning}\n"
            f"LITERAL WORDING: {entry.literal_translation or 'Not supplied'}\n"
            f"MATCHABLE DIACRITIZED VARIATIONS:\n"
            f"{chr(10).join(variations) if variations else '- None supplied'}\n"
            f"ALTERNATIVE CONTEXT MEANINGS: "
            f"{entry.alternative_context_meanings or 'None supplied'}"
        )
    return "\n\n".join(blocks)


TRANSLATION_INSTRUCTIONS = """You are a careful Arabic Islamic-sermon translator.
Translate only the supplied Arabic segment into the requested target language.

Success criteria:
- Preserve every claim, qualification, Qur'anic quotation, hadith, name, and legal term.
- Use supplied canonical wording when it supports the Arabic quotation.
- For an English Qur'an or hadith quotation backed by a CANONICAL WORDING excerpt, copy the
  applicable canonical English wording exactly. Do not paraphrase, smooth, or re-translate it.
- Put supporting raw SOURCE ID values only in the citations array. Do not write SOURCE ID values,
  [S:...] markers, URLs, or citation metadata inside the translation text.
- Do not add commentary, rulings, or facts that are absent from the Arabic.
- When an Arabic religious, technical, or genuinely ambiguous term has no precise natural English
  equivalent, give the best concise English wording followed immediately by the exact Arabic term
  in parentheses, for example: God-consciousness (التقوى). Do this only for genuinely difficult
  terms, not ordinary Arabic words. Put each exact Arabic term in uncertain_terms as well.
- GLOSSARY CANDIDATES are spelling matches from a mosque-supplied glossary. A candidate can have a
  different sense in context and may list diacritized verb, participle, plural, or phrase
  variations. Use the meaning belonging to the exact vocalization and grammatical form in the
  Arabic segment. When it fits, choose a concise natural English word or complete expression,
  follow the whole English expression immediately with the exact Arabic form in parentheses, and
  include that exact Arabic form in uncertain_terms. For a supplied variation, prefer one of that
  variation's concise English renderings when it fits. Never attach the Arabic parenthesis to only
  the final word of a multi-word English expression. Do not copy the glossary explanation into the
  sermon. When the sense does not fit, ignore the candidate.
- For every cited source that has ARABIC SOURCE text, return a Latin-letter transliteration in
  source_transliterations using that source's exact raw SOURCE ID. A transliteration represents the
  Arabic sounds; it is not another English translation. Copy any supplied CANONICAL
  TRANSLITERATION exactly. Otherwise transliterate the authenticated Arabic source carefully.
- If canonical wording conflicts with the Arabic segment, translate the Arabic and flag the term.
- A segment may have no canonical excerpt. Translate its ordinary prose faithfully, and do not
  invent a citation.
- If this segment reveals the khutba's main topic or contains a heading, return a concise natural
  title in the target language in suggested_title (at most 12 words). Otherwise return null. The
  title is metadata: do not add a new title line to the translated sermon text.

Return the structured result only. Citations are evidence for reviewer inspection, not proof of
infallibility. A human reviewer will approve or amend the result before publication."""

VERIFICATION_INSTRUCTIONS = """Act as an independent bilingual Islamic-content verifier.
Compare the Arabic segment word-for-word and claim-for-claim with the proposed translation and
the canonical excerpts. Flag omissions, additions, polarity changes, number/name errors,
mistranslated technical terms, unsupported source wording, and altered Qur'an or hadith quotations.
Set passed to false for any material problem and provide a complete corrected_translation.
Never claim certainty that the evidence does not support. When the target is English, canonical
Qur'an and hadith wording must be preserved exactly wherever the corresponding Arabic quotation
is present. Ensure every difficult or genuinely ambiguous Arabic religious term is rendered as
concise English immediately followed by its exact Arabic term in parentheses. Review the proposed
translation against the GLOSSARY CANDIDATES. Apply a glossary meaning only when its exact sense fits
the segment; otherwise ignore that spelling match. When a candidate does fit, preserve its exact
vocalized Arabic form in parentheses immediately after the complete corresponding English word or
expression so the reader can open the reviewed glossary explanation, and return that exact Arabic
form in uncertain_terms. Return only terms whose glossary sense actually applies in this context;
backend code will repair a missing parenthetical deterministically. Do not attach the Arabic
parenthesis to only the final word of a multi-word expression. Review the
proposed source transliterations against each ARABIC SOURCE. Return a corrected Latin
transliteration for every source with Arabic text, using its exact raw SOURCE ID; copy a supplied
CANONICAL TRANSLITERATION exactly. Never include SOURCE ID values or [S:...] markers in
corrected_translation. Return the structured result only."""

SUNNAH_WEB_SEARCH_INSTRUCTIONS = """Determine whether the supplied Arabic search excerpt is from a
hadith by searching Sunnah.com. Search only the allowed Sunnah.com domain and rely only on pages you
find, never on memory. Prioritize Sahih Muslim, then Sahih al-Bukhari, then Jami` at-Tirmidhi, while
still returning a closer authentic match from another Sunnah.com collection when appropriate.
Return the three strongest candidates at most. A candidate is valid only when its Sunnah.com page
visibly contains matching Arabic hadith wording and its authentic English translation. Copy the
complete relevant Arabic and English wording from the page, not merely the shortened search
excerpt. A Qur'an verse merely quoted inside a hadith page is still Qur'an and must not be returned
as a hadith candidate. Include the page URL, collection slug, hadith number, page title, and grade
if shown. A direct hadith page is preferred, but a Sunnah.com collection/book page containing the
exact hadith is acceptable. If the excerpt is not a hadith or no matching page is found, return no
candidates and no issues. Use issues only when search is inaccessible or evidence is genuinely
ambiguous. Do not use Qur'an pages, blogs, snippets from other sites, or invented references."""


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
        self,
        arabic_text: str,
        target_language: str,
        sources: list[RetrievedSource],
        glossary_entries: list[GlossaryEntry] | None = None,
    ) -> TranslationDraft:
        response = await self.client.responses.parse(
            model=self.translation_model,
            reasoning={"effort": self.reasoning_effort},
            instructions=TRANSLATION_INSTRUCTIONS,
            input=(
                f"TARGET LANGUAGE: {target_language}\n\n"
                f"ARABIC SEGMENT:\n{arabic_text}\n\n"
                f"GLOSSARY CANDIDATES:\n{_glossary_context(glossary_entries)}\n\n"
                f"CANONICAL EXCERPTS:\n{_source_context(sources)}"
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
        source_transliterations: list[SourceTransliteration] | None = None,
        glossary_entries: list[GlossaryEntry] | None = None,
    ) -> VerificationResult:
        proposed_transliterations = json.dumps(
            [item.model_dump() for item in source_transliterations or []],
            ensure_ascii=False,
        )
        response = await self.client.responses.parse(
            model=self.verifier_model,
            reasoning={"effort": self.reasoning_effort},
            instructions=VERIFICATION_INSTRUCTIONS,
            input=(
                f"TARGET LANGUAGE: {target_language}\n\n"
                f"ARABIC SEGMENT:\n{arabic_text}\n\n"
                f"PROPOSED TRANSLATION:\n{translation}\n\n"
                f"GLOSSARY CANDIDATES:\n{_glossary_context(glossary_entries)}\n\n"
                f"PROPOSED SOURCE TRANSLITERATIONS:\n{proposed_transliterations}\n\n"
                f"CANONICAL EXCERPTS:\n{_source_context(sources)}"
            ),
            store=False,
            text_format=VerificationResult,
        )
        if response.output_parsed is None:
            raise RuntimeError("The verification model did not return a structured result")
        return response.output_parsed

    async def search_sunnah(self, arabic_passage: str) -> SunnahWebSearchResult:
        response = await self.client.responses.parse(
            model=self.translation_model,
            reasoning={"effort": "low"},
            instructions=SUNNAH_WEB_SEARCH_INSTRUCTIONS,
            input=f"ARABIC HADITH PASSAGE:\n{arabic_passage}",
            tools=[
                {
                    "type": "web_search",
                    "filters": {"allowed_domains": ["sunnah.com"]},
                    "search_context_size": "low",
                }
            ],
            tool_choice="required",
            include=["web_search_call.action.sources"],
            max_tool_calls=3,
            store=False,
            text_format=SunnahWebSearchResult,
        )
        if response.output_parsed is None:
            raise RuntimeError("Sunnah.com web search did not return a structured result")
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
        self,
        arabic_text: str,
        target_language: str,
        sources: list[RetrievedSource],
        glossary_entries: list[GlossaryEntry] | None = None,
    ) -> TranslationDraft:
        schema = json.dumps(TranslationDraft.model_json_schema())
        data = await self._json(
            self.translation_model,
            TRANSLATION_INSTRUCTIONS,
            f"JSON SCHEMA: {schema}\nTARGET: {target_language}\nARABIC: {arabic_text}\n"
            f"GLOSSARY CANDIDATES:\n{_glossary_context(glossary_entries)}\n"
            f"SOURCES:\n{_source_context(sources)}",
        )
        return TranslationDraft.model_validate(data)

    async def verify(
        self,
        arabic_text: str,
        translation: str,
        target_language: str,
        sources: list[RetrievedSource],
        source_transliterations: list[SourceTransliteration] | None = None,
        glossary_entries: list[GlossaryEntry] | None = None,
    ) -> VerificationResult:
        schema = json.dumps(VerificationResult.model_json_schema())
        proposed_transliterations = json.dumps(
            [item.model_dump() for item in source_transliterations or []],
            ensure_ascii=False,
        )
        data = await self._json(
            self.verifier_model,
            VERIFICATION_INSTRUCTIONS,
            f"JSON SCHEMA: {schema}\nTARGET: {target_language}\nARABIC: {arabic_text}\n"
            f"TRANSLATION: {translation}\n"
            f"GLOSSARY CANDIDATES:\n{_glossary_context(glossary_entries)}\n"
            f"PROPOSED SOURCE TRANSLITERATIONS: {proposed_transliterations}\n"
            f"SOURCES:\n{_source_context(sources)}",
        )
        return VerificationResult.model_validate(data)


class MockProvider(TranslationProvider):
    name = "mock"
    model_name = "deterministic-test-provider"

    async def translate(
        self,
        arabic_text: str,
        target_language: str,
        sources: list[RetrievedSource],
        glossary_entries: list[GlossaryEntry] | None = None,
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
        source_transliterations: list[SourceTransliteration] | None = None,
        glossary_entries: list[GlossaryEntry] | None = None,
    ) -> VerificationResult:
        return VerificationResult(
            passed=True,
            source_transliterations=source_transliterations or [],
        )
