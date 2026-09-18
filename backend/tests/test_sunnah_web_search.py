import asyncio
from types import SimpleNamespace

import pytest

from app.services.canonical_sources import CanonicalRetrieval
from app.services.providers.base import SunnahWebCandidate, SunnahWebSearchResult
from app.services.providers.openai_provider import OpenAIResponsesProvider
from app.services.retrieval import RetrievedSource
from app.services.translation import (
    _canonical_sources_for_segment,
    _sunnah_web_fallback,
    _validated_sunnah_source,
)


def _candidate(url: str = "https://sunnah.com/bukhari:1") -> SunnahWebCandidate:
    return SunnahWebCandidate(
        collection="bukhari",
        hadith_number="1",
        title="Sahih al-Bukhari 1",
        arabic_text="إنما الأعمال بالنيات",
        english_text="The reward of deeds depends upon the intentions.",
        url=url,
        grade="Sahih",
    )


def test_sunnah_web_candidate_requires_matching_arabic_and_domain():
    source = _validated_sunnah_source(
        _candidate(),
        "إنما الأعمال بالنيات",
        "قال رسول الله صلى الله عليه وسلم: إنما الأعمال بالنيات",
    )
    assert source is not None
    assert source.source_id == "sunnah.com:bukhari:1"
    assert source.url == "https://sunnah.com/bukhari:1"

    book_page_source = _validated_sunnah_source(
        _candidate("https://sunnah.com/bukhari/1"),
        "إنما الأعمال بالنيات",
        "قال رسول الله صلى الله عليه وسلم: إنما الأعمال بالنيات",
    )
    assert book_page_source is not None
    assert book_page_source.url == "https://sunnah.com/bukhari:1"

    titled_collection_source = _validated_sunnah_source(
        _candidate("https://sunnah.com/muslim%3A2607c").model_copy(
            update={
                "collection": "Sahih Muslim",
                "hadith_number": "2607c",
                "title": "Sahih Muslim 2607c",
            }
        ),
        "إنما الأعمال بالنيات",
        "قال رسول الله صلى الله عليه وسلم: إنما الأعمال بالنيات",
    )
    assert titled_collection_source is not None
    assert titled_collection_source.source_id == "sunnah.com:muslim:2607c"
    assert titled_collection_source.display_reference == "Sahih Muslim 2607c"

    nested_book_page_source = _validated_sunnah_source(
        _candidate("https://sunnah.com/bukhari/78/96").model_copy(
            update={"collection": "Sahih al-Bukhari", "hadith_number": "6066"}
        ),
        "إنما الأعمال بالنيات",
        "قال رسول الله صلى الله عليه وسلم: إنما الأعمال بالنيات",
    )
    assert nested_book_page_source is not None
    assert nested_book_page_source.source_id == "sunnah.com:bukhari:6066"

    nested_named_book_source = _validated_sunnah_source(
        _candidate("https://sunnah.com/riyadussalihin/introduction/60").model_copy(
            update={"collection": "Riyad as-Salihin", "hadith_number": "60"}
        ),
        "إنما الأعمال بالنيات",
        "قال رسول الله صلى الله عليه وسلم: إنما الأعمال بالنيات",
    )
    assert nested_named_book_source is not None
    assert nested_named_book_source.source_id == "sunnah.com:riyadussalihin:60"

    assert (
        _validated_sunnah_source(
            _candidate("https://example.com/bukhari:1"),
            "إنما الأعمال بالنيات",
            "قال رسول الله صلى الله عليه وسلم: إنما الأعمال بالنيات",
        )
        is None
    )
    mismatched = _candidate().model_copy(update={"arabic_text": "الدين النصيحة"})
    assert (
        _validated_sunnah_source(
            mismatched,
            "إنما الأعمال بالنيات",
            "قال رسول الله صلى الله عليه وسلم: إنما الأعمال بالنيات",
        )
        is None
    )

    conflicting_collection = _candidate().model_copy(update={"collection": "Sahih Muslim"})
    assert (
        _validated_sunnah_source(
            conflicting_collection,
            "إنما الأعمال بالنيات",
            "قال رسول الله صلى الله عليه وسلم: إنما الأعمال بالنيات",
        )
        is None
    )


@pytest.mark.asyncio
async def test_openai_sunnah_search_is_restricted_to_sunnah_dot_com():
    captured = {}
    expected = SunnahWebSearchResult(candidates=[_candidate()])

    class FakeResponses:
        async def parse(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(output_parsed=expected)

    provider = OpenAIResponsesProvider(api_key="test", model="gpt-5.6")
    provider.client = SimpleNamespace(responses=FakeResponses())

    result = await provider.search_sunnah("إنما الأعمال بالنيات")

    assert result == expected
    assert captured["tool_choice"] == "required"
    assert captured["tools"][0]["filters"]["allowed_domains"] == ["sunnah.com"]
    assert "Prioritize Sahih Muslim" in captured["instructions"]


@pytest.mark.asyncio
async def test_sunnah_fallback_checks_every_unsourced_bounded_passage():
    existing = RetrievedSource(
        chunk_id="canonical:sunnah:bukhari:1",
        source_id="sunnah.com:bukhari:1",
        title="Sahih al-Bukhari 1",
        authority="Sunnah.com",
        text="Actions are judged by intentions.",
        score=10_000,
        source_kind="hadith",
        arabic_text="إنما الأعمال بالنيات",
    )
    searched: list[str] = []

    class FakeProvider:
        async def search_sunnah(self, passage):
            searched.append(passage)
            if "الدين النصيحة" in passage:
                return SunnahWebSearchResult(
                    candidates=[
                        SunnahWebCandidate(
                            collection="muslim",
                            hadith_number="55",
                            title="Sahih Muslim 55",
                            arabic_text="الدين النصيحة قلنا لمن قال لله ولكتابه",
                            english_text=(
                                "The religion is sincerity. We said: To whom? He said: "
                                "To Allah and His Book."
                            ),
                            url="https://sunnah.com/muslim:55",
                            grade="Sahih",
                        )
                    ]
                )
            return SunnahWebSearchResult()

    sermon = (
        "«إنما الأعمال بالنيات» ثم قال: [الدين النصيحة قلنا لمن قال لله ولكتابه] "
        "ثم ذكر (هذه حكمة نافعة للناس)."
    )
    sources, issues = await _sunnah_web_fallback(FakeProvider(), sermon, [existing])

    assert all("إنما الأعمال بالنيات" not in passage for passage in searched)
    assert any("الدين النصيحة" in passage for passage in searched)
    assert any("هذه حكمة نافعة" in passage for passage in searched)
    assert [source.source_id for source in sources] == ["sunnah.com:muslim:55"]
    assert issues == []


@pytest.mark.asyncio
async def test_sunnah_fallback_limits_concurrency_and_shortens_long_queries():
    active = 0
    maximum_active = 0
    searched: list[str] = []

    class FakeProvider:
        async def search_sunnah(self, passage):
            nonlocal active, maximum_active
            searched.append(passage)
            active += 1
            maximum_active = max(maximum_active, active)
            await asyncio.sleep(0.01)
            active -= 1
            return SunnahWebSearchResult()

    passages = [" ".join([f"كلمة{i}", *[f"نص{index}" for index in range(1, 16)]]) for i in range(6)]
    sermon = " ".join(f"«{passage}»" for passage in passages)

    await _sunnah_web_fallback(FakeProvider(), sermon, [], max_concurrency=2)

    assert maximum_active <= 2
    assert len(searched) == 6
    assert all(len(query.split()) <= 15 for query in searched)


@pytest.mark.asyncio
async def test_sunnah_fallback_prefers_requested_collections_for_equal_matches():
    class FakeProvider:
        async def search_sunnah(self, passage):
            return SunnahWebSearchResult(
                candidates=[
                    _candidate().model_copy(
                        update={
                            "collection": "abudawud",
                            "hadith_number": "1",
                            "title": "Sunan Abi Dawud 1",
                            "url": "https://sunnah.com/abudawud:1",
                        }
                    ),
                    _candidate().model_copy(
                        update={
                            "collection": "tirmidhi",
                            "hadith_number": "1",
                            "title": "Jami at-Tirmidhi 1",
                            "url": "https://sunnah.com/tirmidhi:1",
                        }
                    ),
                    _candidate().model_copy(
                        update={
                            "collection": "muslim",
                            "hadith_number": "1",
                            "title": "Sahih Muslim 1",
                            "url": "https://sunnah.com/muslim:1",
                        }
                    ),
                ]
            )

    sources, issues = await _sunnah_web_fallback(
        FakeProvider(), "قال الخطيب: «إنما الأعمال بالنيات»", []
    )

    assert issues == []
    assert [source.source_id for source in sources] == ["sunnah.com:muslim:1"]


@pytest.mark.asyncio
async def test_sunnah_fallback_reports_the_specific_rejection_reason():
    class FakeProvider:
        async def search_sunnah(self, passage):
            return SunnahWebSearchResult(
                candidates=[_candidate().model_copy(update={"arabic_text": "الدين النصيحة"})]
            )

    sources, issues = await _sunnah_web_fallback(
        FakeProvider(), "قال الخطيب: «إنما الأعمال بالنيات»", []
    )

    assert sources == []
    assert "Arabic overlap was 0%, below the required 70%" in issues[0]


@pytest.mark.asyncio
async def test_source_classification_runs_hadith_search_before_quran_lookup():
    order: list[str] = []

    class FakeProvider:
        async def search_sunnah(self, passage):
            order.append("sunnah")
            return SunnahWebSearchResult()

    class FakeCanonicalService:
        async def retrieve_hadith(self, value):
            order.append("hadith")
            return CanonicalRetrieval([], [])

        async def retrieve_quran(self, value):
            order.append("quran")
            return CanonicalRetrieval([], [])

    result = await _canonical_sources_for_segment(
        FakeProvider(),
        FakeCanonicalService(),
        "قال الخطيب: «هذه جملة عربية عادية»",
        sunnah_web_search_enabled=True,
    )

    assert order == ["hadith", "sunnah", "quran"]
    assert result == CanonicalRetrieval([], [])
