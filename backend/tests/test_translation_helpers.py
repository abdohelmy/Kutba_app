from app.api.routes.reader import _deduplicate_reader_citations
from app.services.providers.base import SourceTransliteration
from app.services.retrieval import RetrievedSource
from app.services.translation import (
    _ambiguous_term_issues,
    _canonical_wording_issues,
    _citation_payloads,
    _normalize_source_id,
    _normalized_transliterations,
    _sanitize_translation_source_markers,
)


def test_ambiguous_term_requires_parenthesized_arabic_after_english_wording():
    assert _ambiguous_term_issues("God-consciousness (التقوى)", ["التقوى"]) == []
    assert _ambiguous_term_issues("God-consciousness means التقوى", ["التقوى"]) == [
        "Ambiguous term التقوى must appear in parentheses immediately after its English wording"
    ]


def test_generated_transliteration_must_be_latin_and_reference_a_known_source():
    source = RetrievedSource(
        chunk_id="canonical:sunnah:bukhari:1",
        source_id="sunnah.com:bukhari:1",
        title="Sahih al-Bukhari 1",
        authority="Sunnah.com",
        text="Actions are judged by intentions.",
        score=10_000,
    )
    allowed = {source.chunk_id: source}
    items = [
        SourceTransliteration(
            source_id=source.chunk_id,
            transliteration="Innama al-a'malu bil-niyyat",
        ),
        SourceTransliteration(
            source_id="unknown",
            transliteration="Unknown source",
        ),
        SourceTransliteration(
            source_id=source.chunk_id,
            transliteration="إنما الأعمال بالنيات",
        ),
    ]

    # The later invalid Arabic value is ignored rather than replacing the valid Latin value.
    assert _normalized_transliterations(items, allowed) == {
        source.chunk_id: "Innama al-a'malu bil-niyyat"
    }


def test_source_markers_are_removed_from_reader_text_and_structured_ids_are_normalized():
    source = RetrievedSource(
        chunk_id="canonical:quran:2:152",
        source_id="quran.com:2:152",
        title="Al-Baqarah 2:152",
        authority="Quran.com",
        text="So remember Me; I will remember you.",
        score=10_000,
    )
    allowed = {source.chunk_id: source}

    cleaned, issues = _sanitize_translation_source_markers(
        "So remember Me [S:canonical:quran:2:152], and be grateful.",
        allowed,
    )

    assert cleaned == "So remember Me, and be grateful."
    assert issues == []
    assert _normalize_source_id("[S:canonical:quran:2:152]") == source.chunk_id


def test_unknown_inline_source_marker_is_removed_and_flagged():
    cleaned, issues = _sanitize_translation_source_markers(
        "Translated text [S:invented:source].",
        {},
    )

    assert cleaned == "Translated text."
    assert issues == [
        "The model inserted an unknown source marker (invented:source); it was removed"
    ]


def test_partial_canonical_wording_produces_exact_citation_offsets():
    source = RetrievedSource(
        chunk_id="canonical:quran:2:255",
        source_id="quran.com:2:255",
        title="Al-Baqarah 2:255",
        authority="Quran.com",
        text="Allah - there is no deity except Him, the Ever-Living, the Self-Sustaining.",
        score=10_000,
        source_kind="quran",
        minimum_verbatim_words=4,
    )
    translated = "Remember that there is no deity except Him, then remain steadfast."

    citations = _citation_payloads(source, translated, None)

    assert citations[0]["excerpt"] == "there is no deity except Him"
    start = citations[0]["translation_start"]
    end = citations[0]["translation_end"]
    assert translated[start:end] == citations[0]["excerpt"]
    assert _canonical_wording_issues(translated, "en", [source]) == []
    assert _canonical_wording_issues("A paraphrase only.", "en", [source])


def test_reader_hides_quran_citation_already_contained_in_hadith_source():
    citations = [
        {
            "source_kind": "quran",
            "arabic_excerpt": "كلا بل ران على قلوبهم ما كانوا يكسبون",
            "title": "Al-Mutaffifin 83:14",
        },
        {
            "source_kind": "hadith",
            "arabic_excerpt": ("وهو الران الذي ذكر الله كلا بل ران على قلوبهم ما كانوا يكسبون"),
            "title": "Jami at-Tirmidhi 3334",
        },
    ]

    assert _deduplicate_reader_citations(citations) == [citations[1]]
