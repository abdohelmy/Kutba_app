import httpx
import pytest

from app.core.config import Settings
from app.services.canonical_sources import (
    CanonicalSourceService,
    QuranVerse,
    arabic_passages_match,
    bounded_passage_candidates,
    deduplicate_embedded_quran_sources,
    detect_hadith_references,
    detect_numeric_quran_references,
    hadith_passages_match,
    hadith_search_excerpt,
    hadith_search_passage,
    hadith_web_search_candidates,
    has_hadith_cue,
    normalize_arabic_words,
    quran_passage_candidates,
)
from app.services.retrieval import RetrievedSource, SourceOccurrence


def test_detects_explicit_quran_and_hadith_references():
    assert detect_numeric_quran_references("قال تعالى (٢:٢٥٥-٢٥٦)") == {"2:255", "2:256"}
    references = detect_hadith_references("رَوَاهُ الْبُخَارِيُّ، حَدِيثٌ رَقْمُ ١")
    assert [(item.collection, item.hadith_number) for item in references] == [("bukhari", "1")]


def test_numeric_quran_reference_requires_quran_context():
    assert detect_numeric_quran_references("موعد الدرس (2:30)") == set()
    assert detect_numeric_quran_references("﴿نص الآية﴾ (2:255)") == {"2:255"}


def test_named_quran_reference_supports_bounded_surah_name_without_false_bare_match():
    service = CanonicalSourceService(Settings(translation_provider="mock"), httpx.AsyncClient())
    service._quran_chapters = {20: "طه"}

    assert service._detect_named_quran_references("[طه: 124]") == {"20:124"}
    assert service._detect_named_quran_references("سورة طه الآية 124") == {"20:124"}
    assert service._detect_named_quran_references("بدأ الدرس طه 124 دقيقة") == set()


@pytest.mark.parametrize("honorific", ["ﷺ", "ؐ", "صَلَّى اللهُ عَلَيْهِ وَسَلَّمَ", "صلعم"])
def test_hadith_honorifics_mark_the_following_quotation_as_a_candidate(honorific):
    value = f"النبي {honorific}: «إِنَّمَا الْأَعْمَالُ بِالنِّيَّاتِ»"

    assert has_hadith_cue(value)
    assert arabic_passages_match(hadith_search_passage(value) or "", "إنما الأعمال بالنيات")


def test_bounded_quotation_is_checked_even_without_an_explicit_cue():
    assert (
        hadith_search_passage("ومن الوصايا: “الدين النصيحة للمسلمين” ثم تابع الخطبة")
        == "الدين النصيحة للمسلمين"
    )


def test_hadith_matching_requires_seventy_percent_ordered_word_overlap():
    passage = "واحد اثنان ثلاثة أربعة خمسة ستة سبعة ثمانية تسعة عشرة"

    assert hadith_passages_match(
        passage,
        "واحد اثنان ثلاثة أربعة خمسة ستة سبعة مختلف مختلف مختلف",
    )
    assert not hadith_passages_match(
        passage,
        "واحد اثنان ثلاثة أربعة خمسة ستة مختلف مختلف مختلف مختلف",
    )


def test_web_search_checks_unquoted_speech_after_qala_rasul_allah():
    candidates = hadith_web_search_candidates(
        "قال رسول الله ﷺ: إنما الأعمال بالنيات ولكل امرئ ما نوى. ثم شرح الخطيب."
    )

    assert [candidate.text for candidate in candidates] == ["انما الاعمال بالنيات ولكل امري ما نوي"]


def test_web_search_keeps_a_quoted_block_whole_and_limits_the_query():
    quote = (
        "الجملة الأولى فيها كلمات كثيرة للبحث. "
        "الجملة الثانية فيها كلمات كثيرة للبحث. "
        "الجملة الثالثة فيها كلمات كثيرة للبحث. "
        "الجملة الرابعة يجب ألا تدخل في البحث."
    )

    candidates = hadith_web_search_candidates(f"قال الخطيب: «{quote}»")
    query = hadith_search_excerpt(candidates[0].text)

    assert [candidate.text for candidate in candidates] == [quote]
    assert len(query.split()) <= 15
    assert "الجملة الثالثة" in query
    assert "الجملة الرابعة" not in query


def test_long_bounded_hadith_is_not_dropped():
    quote = " ".join(["كلمة"] * 220)

    assert hadith_web_search_candidates(f"«{quote}»")


@pytest.mark.parametrize(
    "bounded",
    [
        "﴿إنما الأعمال بالنيات﴾",
        "«إنما الأعمال بالنيات»",
        "“إنما الأعمال بالنيات”",
        "‘إنما الأعمال بالنيات’",
        "❝إنما الأعمال بالنيات❞",
        "‹إنما الأعمال بالنيات›",
        "「إنما الأعمال بالنيات」",
        "『إنما الأعمال بالنيات』",
        "《إنما الأعمال بالنيات》",
        "〈إنما الأعمال بالنيات〉",
        '"إنما الأعمال بالنيات"',
        "'إنما الأعمال بالنيات'",
        "(إنما الأعمال بالنيات)",
        "[إنما الأعمال بالنيات]",
        "{إنما الأعمال بالنيات}",
        "（إنما الأعمال بالنيات）",
        "【إنما الأعمال بالنيات】",
        "〔إنما الأعمال بالنيات〕",
    ],
)
def test_common_quotation_and_bracket_styles_are_all_bounded(bounded):
    candidates = bounded_passage_candidates(f"قبل النص {bounded} بعد النص")

    assert any(
        arabic_passages_match(candidate.text, "إنما الأعمال بالنيات") for candidate in candidates
    )


def test_multiple_sentences_inside_one_quote_are_checked_separately():
    candidates = bounded_passage_candidates("قال: «إنما الأعمال بالنيات. الدين النصيحة لكل مسلم.»")

    assert [candidate.text for candidate in candidates] == [
        "إنما الأعمال بالنيات.",
        "الدين النصيحة لكل مسلم.",
    ]


def test_numbered_short_quran_verses_are_split_and_resolved_with_exact_offsets():
    first = "أَلۡهَىٰكُمُ ٱلتَّكَاثُرُ"
    second = "حَتَّىٰ زُرۡتُمُ ٱلۡمَقَابِرَ"
    sermon_text = f'قال تعالى "{first} (1) {second} (2)"'
    candidates = [
        candidate
        for candidate in quran_passage_candidates(sermon_text)
        if candidate.reason == "numbered Qur'an verse"
    ]

    assert [candidate.text for candidate in candidates] == [first, second]
    assert all(
        sermon_text[candidate.start : candidate.end] == candidate.text for candidate in candidates
    )

    service = CanonicalSourceService(Settings(translation_provider="mock"), httpx.AsyncClient())
    service._quran_verses = {
        "102:1": QuranVerse("102:1", first, normalize_arabic_words(first)),
        "102:2": QuranVerse("102:2", second, normalize_arabic_words(second)),
    }
    for key, verse in service._quran_verses.items():
        for index in range(len(verse.normalized_words) - 1):
            service._quran_bigram_index.setdefault(
                verse.normalized_words[index : index + 2], set()
            ).add(key)

    matches, verbatim, occurrences, _minimums, issues = service._detect_quoted_quran_verses(
        sermon_text
    )

    assert matches == {"102:1", "102:2"}
    assert verbatim == matches
    assert issues == []
    assert occurrences["102:1"][0].arabic_text == first
    assert occurrences["102:2"][0].arabic_text == second


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            "وقد صور النبي ﷺ الأثر فقال:\n\nإِنَّ العَبْدَ إِذَا أَخْطَأَ "
            "نُكِتَتْ فِي قَلْبِهِ نُكْتَةٌ سَوْدَاءُ» [رواه الترمذي]",
            "ان العبد اذا اخطا نكتت في قلبه نكتة سوداء",
        ),
        (
            "ضرب النبي ﷺ مثلا فقال عليه الصلاة والسلام: مَثَلُ الَّذِي يَذْكُرُ "
            "رَبَّهُ مَثَلُ الحَيِّ وَالمَيِّتِ» [رواه البخاري]",
            "مثل الذي يذكر ربه مثل الحي والميت",
        ),
    ],
)
def test_hadith_search_uses_words_after_speech_attribution(value, expected):
    assert hadith_search_passage(value) == expected


def test_quran_source_embedded_inside_hadith_is_not_duplicated():
    hadith = RetrievedSource(
        chunk_id="canonical:sunnah:tirmidhi:3334",
        source_id="sunnah.com:tirmidhi:3334",
        title="Jami at-Tirmidhi 3334",
        authority="Sunnah.com",
        text="The stain is what Allah mentioned in the verse.",
        score=10_000,
        source_kind="hadith",
        arabic_text=("وهو الران الذي ذكر الله كلا بل ران على قلوبهم ما كانوا يكسبون"),
    )
    embedded_quran = RetrievedSource(
        chunk_id="canonical:quran:83:14",
        source_id="quran.com:83:14",
        title="Al-Mutaffifin 83:14",
        authority="Quran.com",
        text="No! Rather, the stain has covered their hearts.",
        score=10_000,
        source_kind="quran",
        arabic_text="كلا بل ران على قلوبهم ما كانوا يكسبون",
    )
    separate_quran = RetrievedSource(
        chunk_id="canonical:quran:20:124",
        source_id="quran.com:20:124",
        title="Taha 20:124",
        authority="Quran.com",
        text="Whoever turns away from My remembrance will have a difficult life.",
        score=10_000,
        source_kind="quran",
        arabic_text="ومن أعرض عن ذكري فإن له معيشة ضنكا",
    )

    assert deduplicate_embedded_quran_sources([embedded_quran, separate_quran, hadith]) == [
        separate_quran,
        hadith,
    ]


def test_embedded_quran_deduplication_preserves_a_separate_occurrence():
    quran = RetrievedSource(
        chunk_id="canonical:quran:83:14",
        source_id="quran.com:83:14",
        title="Al-Mutaffifin 83:14",
        authority="Quran.com",
        text="No! Rather, the stain has covered their hearts.",
        score=10_000,
        source_kind="quran",
        arabic_text="كلا بل ران على قلوبهم",
        occurrences=(
            SourceOccurrence("كلا بل ران على قلوبهم", 20, 45),
            SourceOccurrence("كلا بل ران على قلوبهم", 120, 145),
        ),
    )
    hadith = RetrievedSource(
        chunk_id="canonical:sunnah:tirmidhi:3334",
        source_id="sunnah.com:tirmidhi:3334",
        title="Jami at-Tirmidhi 3334",
        authority="Sunnah.com",
        text="The stain is what Allah mentioned.",
        score=10_000,
        source_kind="hadith",
        arabic_text="وهو الران كلا بل ران على قلوبهم",
        occurrences=(SourceOccurrence("وهو الران كلا بل ران على قلوبهم", 10, 55),),
    )

    result = deduplicate_embedded_quran_sources([quran, hadith])

    assert result[0].occurrences == (SourceOccurrence("كلا بل ران على قلوبهم", 120, 145),)
    assert result[1] == hadith


def test_ambiguous_partial_quran_match_fails_closed():
    service = CanonicalSourceService(Settings(translation_provider="mock"), httpx.AsyncClient())
    words = ("قول", "مشترك", "بين", "ايتين")
    service._quran_verses = {
        "2:1": QuranVerse("2:1", "قول مشترك بين آيتين أولى", (*words, "اولي")),
        "3:1": QuranVerse("3:1", "قول مشترك بين آيتين ثانية", (*words, "ثانية")),
    }
    for key, verse in service._quran_verses.items():
        for index in range(len(verse.normalized_words) - 1):
            service._quran_bigram_index.setdefault(
                verse.normalized_words[index : index + 2], set()
            ).add(key)

    matches, _verbatim, _occurrences, _minimums, issues = service._detect_quoted_quran_verses(
        "قال تعالى: «قول مشترك بين آيتين»"
    )

    assert matches == set()
    assert "matched multiple verses" in issues[0]


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
                                "ٱللَّهُ لَآ إِلَـٰهَ إِلَّا هُوَ ٱلْحَىُّ ٱلْقَيُّومُ لَا تَأْخُذُهُۥ سِنَةٌ وَلَا نَوْمٌ"
                            ),
                        }
                    ]
                },
            )
        if request.url.path.endswith("/chapters"):
            return httpx.Response(
                200,
                json={
                    "chapters": [{"id": 2, "name_arabic": "البقرة", "name_simple": "Al-Baqarah"}]
                },
            )
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
        if request.url.path.endswith("/quran/translations/57"):
            return httpx.Response(
                200,
                json={
                    "translations": [
                        {
                            "verse_key": "2:255",
                            "resource_name": "Transliteration",
                            "text": "La takhudhuhu sinatun wa-la nawm.",
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
    assert result.sources[0].minimum_verbatim_words >= 3
    assert result.sources[0].occurrences
    assert result.sources[0].display_reference == "Al-Baqarah 2:255"


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
                            "text_uthmani": ("إِنَّهُۥ مِن سُلَيْمَـٰنَ وَإِنَّهُۥ بِسْمِ اللَّهِ الرَّحْمَـٰنِ الرَّحِيمِ"),
                        },
                    ]
                },
            )
        if request.url.path.endswith("/chapters"):
            return httpx.Response(
                200,
                json={
                    "chapters": [
                        {"id": 1, "name_arabic": "الفاتحة", "name_simple": "Al-Fatihah"},
                        {"id": 27, "name_arabic": "النمل", "name_simple": "An-Naml"},
                    ]
                },
            )
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
        if request.url.path.endswith("/quran/translations/57"):
            verse_key = request.url.params["verse_key"]
            return httpx.Response(
                200,
                json={
                    "translations": [
                        {
                            "verse_key": verse_key,
                            "resource_name": "Transliteration",
                            "text": "Bismi Allahi al-rahmani al-raheem",
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
                json={
                    "chapters": [{"id": 1, "name_arabic": "الفاتحة", "name_simple": "Al-Fatihah"}]
                },
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
                                "[All] praise is [due] to Allāh, Lord of the worlds -<sup>1</sup>"
                            ),
                        }
                    ],
                    "meta": {"translation_name": "Saheeh International"},
                },
            )
        if request.url.path.endswith("/quran/translations/57"):
            assert request.url.params["verse_key"] == "1:2"
            return httpx.Response(
                200,
                json={
                    "translations": [
                        {
                            "verse_key": "1:2",
                            "resource_name": "Transliteration",
                            "text": "Al-hamdu lillahi rabbi al-alamin",
                        }
                    ]
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
    assert quran.text == "[All] praise is [due] to Allāh, Lord of the worlds"
    assert quran.url == "https://quran.com/1/2"
    assert quran.verbatim_required is True
    assert quran.transliteration == "Al-hamdu lillahi rabbi al-alamin"
    assert quran.display_reference == "Al-Fatihah 1:2"


@pytest.mark.asyncio
async def test_flags_hadith_when_sunnah_key_is_missing():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/quran/verses/uthmani"):
            return httpx.Response(
                200,
                json={"verses": [{"verse_key": "1:1", "text_uthmani": "بسم الله الرحمن الرحيم"}]},
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
                json={"verses": [{"verse_key": "1:1", "text_uthmani": "بسم الله الرحمن الرحيم"}]},
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
