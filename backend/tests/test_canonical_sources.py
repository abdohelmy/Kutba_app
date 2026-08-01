import httpx
import pytest

from app.core.config import Settings
from app.services.canonical_sources import (
    CanonicalSourceService,
    detect_hadith_references,
    detect_numeric_quran_references,
)


def test_detects_explicit_quran_and_hadith_references():
    assert detect_numeric_quran_references("قال تعالى (٢:٢٥٥-٢٥٦)") == {"2:255", "2:256"}
    references = detect_hadith_references("رَوَاهُ الْبُخَارِيُّ، حَدِيثٌ رَقْمُ ١")
    assert [(item.collection, item.hadith_number) for item in references] == [("bukhari", "1")]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sermon_text",
    [
        "قَالَ اللَّهُ تَعَالَى: «لَا تَأْخُذُهُ سِنَةٌ وَلَا نَوْمٌ»",
        "موضوع الخطبة لَا تَأْخُذُهُ سِنَةٌ وَلَا نَوْمٌ. ثم نتابع الكلام.",
    ],
)
async def test_matches_partial_quran_passages_from_cues_quotes_or_tashkil(sermon_text):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/quran/verses/uthmani"):
            return httpx.Response(
                200,
                json={
                    "verses": [
                        {
                            "verse_key": "2:255",
                            "text_uthmani": (
                                "ٱللَّهُ لَآ إِلَـٰهَ إِلَّا هُوَ ٱلْحَىُّ ٱلْقَيُّومُ "
                                "لَا تَأْخُذُهُۥ سِنَةٌ وَلَا نَوْمٌ"
                            ),
                        }
                    ]
                },
            )
        if request.url.path.endswith("/chapters"):
            return httpx.Response(200, json={"chapters": []})
        if request.url.path.endswith("/quran/translations/20"):
            assert request.url.params["verse_key"] == "2:255"
            return httpx.Response(
                200,
                json={
                    "translations": [
                        {
                            "verse_key": "2:255",
                            "resource_name": "Saheeh International",
                            "text": "Neither drowsiness overtakes Him nor sleep.",
                        }
                    ]
                },
            )
        return httpx.Response(404)

    settings = Settings(
        translation_provider="mock",
        canonical_sources_enabled=True,
        quran_legacy_api_base_url="https://quran.test/api/v4",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await CanonicalSourceService(settings, client).retrieve(sermon_text)

    assert result.issues == []
    assert [source.source_id for source in result.sources] == ["quran.com:2:255"]
    assert result.sources[0].verbatim_required is False


@pytest.mark.asyncio
async def test_basmalah_uses_fatihah_reference_instead_of_naml():
    requested_verses: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/quran/verses/uthmani"):
            return httpx.Response(
                200,
                json={
                    "verses": [
                        {"verse_key": "1:1", "text_uthmani": "بِسْمِ اللَّهِ الرَّحْمَـٰنِ الرَّحِيمِ"},
                        {
                            "verse_key": "27:30",
                            "text_uthmani": (
                                "إِنَّهُۥ مِن سُلَيْمَـٰنَ وَإِنَّهُۥ بِسْمِ اللَّهِ "
                                "الرَّحْمَـٰنِ الرَّحِيمِ"
                            ),
                        },
                    ]
                },
            )
        if request.url.path.endswith("/chapters"):
            return httpx.Response(200, json={"chapters": []})
        if request.url.path.endswith("/quran/translations/20"):
            verse_key = request.url.params["verse_key"]
            requested_verses.append(verse_key)
            return httpx.Response(
                200,
                json={
                    "translations": [
                        {
                            "verse_key": verse_key,
                            "resource_name": "Saheeh International",
                            "text": (
                                "In the name of Allah, the Entirely Merciful, "
                                "the Especially Merciful."
                            ),
                        }
                    ]
                },
            )
        return httpx.Response(404)

    settings = Settings(
        translation_provider="mock",
        canonical_sources_enabled=True,
        quran_legacy_api_base_url="https://quran.test/api/v4",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await CanonicalSourceService(settings, client).retrieve(
            "بِسْمِ اللَّهِ الرَّحْمَنِ الرَّحِيمِ\nموضوع خطبة الجمعة"
        )

    assert requested_verses == ["1:1"]
    assert [source.source_id for source in result.sources] == ["quran.com:1:1"]


@pytest.mark.asyncio
async def test_retrieves_quran_wording_and_sunnah_translation():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/quran/verses/uthmani"):
            return httpx.Response(
                200,
                json={
                    "verses": [
                        {
                            "verse_key": "1:2",
                            "text_uthmani": "ٱلْحَمْدُ لِلَّهِ رَبِّ ٱلْعَـٰلَمِينَ",
                        }
                    ]
                },
            )
        if request.url.path.endswith("/chapters"):
            return httpx.Response(
                200,
                json={"chapters": [{"id": 1, "name_arabic": "الفاتحة"}]},
            )
        if request.url.path.endswith("/quran/translations/20"):
            assert request.url.params["verse_key"] == "1:2"
            return httpx.Response(
                200,
                json={
                    "translations": [
                        {
                            "verse_key": "1:2",
                            "resource_name": "Saheeh International",
                            "text": (
                                "[All] praise is [due] to Allāh, Lord of the worlds -"
                                "<sup>1</sup>"
                            ),
                        }
                    ],
                    "meta": {"translation_name": "Saheeh International"},
                },
            )
        if request.url.path.endswith("/collections/bukhari/hadiths/1"):
            assert request.headers["X-API-Key"] == "test-sunnah-key"
            return httpx.Response(
                200,
                json={
                    "collection": "bukhari",
                    "hadithNumber": "1",
                    "hadith": [
                        {"lang": "ar", "body": "إنما الأعمال بالنيات"},
                        {
                            "lang": "en",
                            "body": "Actions are judged by intentions.",
                            "grades": [{"grade": "Sahih", "graded_by": "Al-Albani"}],
                        },
                    ],
                },
            )
        return httpx.Response(404)

    settings = Settings(
        translation_provider="mock",
        canonical_sources_enabled=True,
        quran_api_mode="legacy",
        quran_legacy_api_base_url="https://quran.test/api/v4",
        quran_translation_id=20,
        sunnah_api_base_url="https://sunnah.test/v1",
        sunnah_api_key="test-sunnah-key",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = CanonicalSourceService(settings, client)
        result = await service.retrieve(
            "الحمد لله رب العالمين. إنما الأعمال بالنيات، رواه البخاري، حديث رقم ١."
        )

    assert result.issues == []
    assert [source.source_kind for source in result.sources] == ["hadith", "quran"]
    hadith, quran = result.sources
    assert hadith.text == "Actions are judged by intentions."
    assert "Sahih — Al-Albani" in hadith.title
    assert hadith.url == "https://sunnah.com/bukhari:1"
    assert hadith.verbatim_required is True
    assert quran.text == "[All] praise is [due] to Allāh, Lord of the worlds -"
    assert quran.url == "https://quran.com/1/2"
    assert quran.verbatim_required is True


@pytest.mark.asyncio
async def test_flags_hadith_when_sunnah_key_is_missing():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/quran/verses/uthmani"):
            return httpx.Response(
                200,
                json={
                    "verses": [
                        {"verse_key": "1:1", "text_uthmani": "بسم الله الرحمن الرحيم"}
                    ]
                },
            )
        if request.url.path.endswith("/chapters"):
            return httpx.Response(200, json={"chapters": []})
        return httpx.Response(404)

    settings = Settings(
        translation_provider="mock",
        canonical_sources_enabled=True,
        quran_legacy_api_base_url="https://quran.test/api/v4",
        sunnah_api_key=None,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await CanonicalSourceService(settings, client).retrieve(
            "قال رسول الله صلى الله عليه وسلم، رواه مسلم حديث رقم 1"
        )

    assert result.sources == []
    assert any("Sunnah.com API key is not configured" in issue for issue in result.issues)


@pytest.mark.asyncio
async def test_detects_vocalized_hadith_cue_without_collection_number():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/quran/verses/uthmani"):
            return httpx.Response(
                200,
                json={
                    "verses": [
                        {"verse_key": "1:1", "text_uthmani": "بسم الله الرحمن الرحيم"}
                    ]
                },
            )
        if request.url.path.endswith("/chapters"):
            return httpx.Response(200, json={"chapters": []})
        return httpx.Response(404)

    settings = Settings(
        translation_provider="mock",
        canonical_sources_enabled=True,
        quran_legacy_api_base_url="https://quran.test/api/v4",
        sunnah_api_key=None,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await CanonicalSourceService(settings, client).retrieve(
            "فِي الْحَدِيثِ: «إِنَّمَا الْأَعْمَالُ بِالنِّيَّاتِ»"
        )

    assert result.sources == []
    assert any(
        "without an exact collection and number" in issue and "Detected passage" in issue
        for issue in result.issues
    )
