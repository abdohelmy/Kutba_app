import asyncio
import html
import re
import time
from dataclasses import dataclass

import httpx

from app.core.config import Settings
from app.services.retrieval import RetrievedSource

ARABIC_MARKS_RE = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
ARABIC_WORD_RE = re.compile(r"[\u0621-\u063A\u0641-\u064A0-9]+")
HTML_TAG_RE = re.compile(r"<[^>]+>")
SUP_RE = re.compile(r"<sup\b[^>]*>.*?</sup>", re.IGNORECASE | re.DOTALL)
SPACE_RE = re.compile(r"\s+")
ARABIC_LETTER_RE = re.compile(r"[\u0621-\u064A\u0671]")
DIGIT_TRANSLATION = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
ARABIC_CHARACTER_TRANSLATION = str.maketrans(
    {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ٱ": "ا",
        "ى": "ي",
        "ؤ": "و",
        "ئ": "ي",
        "ـ": "",
    }
)

QURAN_CUE_RE = re.compile(
    r"(?:بسم\s+الله\s+الرحمن\s+الرحيم|قال\s+(?:الله(?:\s+تعالي)?|تعالي|سبحانه)|"
    r"قال\s+عز\s+وجل|سورة|(?:ال)?اي(?:ة|ات)|[﴿۝])"
)
QURAN_SPEECH_CUE_RE = re.compile(
    r"قال\s+(?:الله(?:\s+تعالي)?|تعالي|سبحانه(?:\s+وتعالي)?|عز\s+وجل)"
)
HADITH_CUE_RE = re.compile(
    r"(?:في\s+الحديث|قال\s+(?:رسول\s+الله|النبي)|عن\s+(?:رسول\s+الله|النبي)|"
    r"رواه\s+(?:البخاري|مسلم|النسائي|ابو\s+داود|ابي\s+داود|الترمذي|ابن\s+ماجه)|"
    r"صلي\s+الله\s+عليه\s+وسلم)",
    re.IGNORECASE,
)
QURAN_NUMERIC_REF_RE = re.compile(
    r"(?<!\d)(?P<chapter>\d{1,3})\s*[:：]\s*(?P<start>\d{1,3})"
    r"(?:\s*[-–—]\s*(?P<end>\d{1,3}))?(?!\d)"
)


@dataclass(frozen=True)
class QuranVerse:
    verse_key: str
    arabic_text: str
    normalized_words: tuple[str, ...]


@dataclass(frozen=True)
class HadithReference:
    collection: str
    collection_title: str
    hadith_number: str


@dataclass(frozen=True)
class CanonicalRetrieval:
    sources: list[RetrievedSource]
    issues: list[str]


@dataclass(frozen=True)
class PassageCandidate:
    text: str
    minimum_match_words: int
    reason: str


COLLECTIONS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "bukhari",
        "Sahih al-Bukhari",
        (r"(?:صحيح\s+)?البخاري", r"sahih\s+al[-\s]?bukhari", r"bukhari"),
    ),
    ("muslim", "Sahih Muslim", (r"(?:صحيح\s+)?مسلم", r"sahih\s+muslim")),
    ("nasai", "Sunan an-Nasa'i", (r"(?:سنن\s+)?النسائي", r"an[-\s]?nasa['’]?i", r"nasai")),
    (
        "abudawud",
        "Sunan Abi Dawud",
        (r"(?:سنن\s+)?(?:أبي|ابي|أبو|ابو)\s+داود", r"(?:abu|abi)\s+dawud"),
    ),
    ("tirmidhi", "Jami` at-Tirmidhi", (r"(?:جامع\s+)?الترمذي", r"tirmidhi")),
    ("ibnmajah", "Sunan Ibn Majah", (r"(?:سنن\s+)?ابن\s+ماجه", r"ibn\s+majah")),
    ("malik", "Muwatta Malik", (r"(?:موطأ|موطا)\s+مالك", r"muwatta\s+malik")),
    (
        "riyadussalihin",
        "Riyad as-Salihin",
        (r"رياض\s+الصالحين", r"riyad\s+(?:as[-\s]?)?salihin"),
    ),
    (
        "nawawi40",
        "Forty Hadith of an-Nawawi",
        (r"(?:الأربعون|الاربعون)\s+النووية", r"nawawi\s*40"),
    ),
    (
        "qudsi40",
        "Forty Hadith Qudsi",
        (r"(?:الأحاديث|الاحاديث)\s+القدسية", r"qudsi\s*40"),
    ),
)


class CanonicalSourceError(RuntimeError):
    pass


def normalize_arabic_words(value: str) -> tuple[str, ...]:
    value = value.translate(DIGIT_TRANSLATION)
    value = ARABIC_MARKS_RE.sub("", value)
    value = value.translate(ARABIC_CHARACTER_TRANSLATION)
    # Uthmani text frequently writes an alif as a dagger mark, while uploaded modern Arabic uses
    # a full alif. Removing alif in this comparison form makes those orthographies comparable.
    value = value.replace("ا", "")
    return tuple(ARABIC_WORD_RE.findall(value.lower()))


def normalize_arabic_cues(value: str) -> str:
    value = value.translate(DIGIT_TRANSLATION)
    value = ARABIC_MARKS_RE.sub("", value)
    return SPACE_RE.sub(" ", value.translate(ARABIC_CHARACTER_TRANSLATION)).strip().lower()


def has_quran_cue(value: str) -> bool:
    return bool(QURAN_CUE_RE.search(normalize_arabic_cues(value)))


def has_hadith_cue(value: str) -> bool:
    return bool(HADITH_CUE_RE.search(normalize_arabic_cues(value)))


def _deduplicate_passages(passages: list[PassageCandidate]) -> list[PassageCandidate]:
    unique: list[PassageCandidate] = []
    seen: set[tuple[str, ...]] = set()
    for passage in passages:
        normalized = normalize_arabic_words(passage.text)
        if len(normalized) >= passage.minimum_match_words and normalized not in seen:
            unique.append(passage)
            seen.add(normalized)
    return unique


def _quoted_passages(value: str) -> list[PassageCandidate]:
    patterns = (
        (re.compile(r"﴿(?P<text>[^﴾]{2,1000})﴾", re.DOTALL), 2, "Qur'an brackets"),
        (re.compile(r"«(?P<text>[^»]{2,1000})»", re.DOTALL), 3, "quotation marks"),
        (re.compile(r"“(?P<text>[^”]{2,1000})”", re.DOTALL), 3, "quotation marks"),
        (re.compile(r'"(?P<text>[^"\n]{2,1000})"'), 3, "quotation marks"),
    )
    return [
        PassageCandidate(match.group("text"), minimum, reason)
        for pattern, minimum, reason in patterns
        for match in pattern.finditer(value)
    ]


def _cue_passages(value: str, cue: re.Pattern[str], reason: str) -> list[PassageCandidate]:
    normalized = normalize_arabic_cues(value)
    passages: list[PassageCandidate] = []
    for match in cue.finditer(normalized):
        remainder = normalized[match.end() :].lstrip(" :：،,-–—")
        candidate = re.split(r"[\n\r.;؛]", remainder, maxsplit=1)[0].strip()
        if candidate:
            passages.append(PassageCandidate(candidate[:1000], 2, reason))
    return passages


def _vocalized_passages(value: str) -> list[PassageCandidate]:
    passages: list[PassageCandidate] = []
    for candidate in re.split(r"[\n\r.;؛]", value):
        candidate = candidate.strip()
        letters = len(ARABIC_LETTER_RE.findall(candidate))
        marks = len(ARABIC_MARKS_RE.findall(candidate))
        if letters >= 10 and marks >= 4 and marks / letters >= 0.1:
            passages.append(PassageCandidate(candidate[:1000], 4, "tashkil"))
    return passages


def quran_passage_candidates(value: str) -> list[PassageCandidate]:
    passages = _quoted_passages(value)
    passages.extend(_cue_passages(value, QURAN_SPEECH_CUE_RE, "Qur'an cue"))
    passages.extend(_vocalized_passages(value))
    return _deduplicate_passages(passages)


def hadith_passage_candidates(value: str) -> list[PassageCandidate]:
    passages = _quoted_passages(value)
    passages.extend(_cue_passages(value, HADITH_CUE_RE, "hadith cue"))
    passages.extend(_vocalized_passages(value))
    return _deduplicate_passages(passages)


def _clean_html(value: str) -> str:
    value = SUP_RE.sub("", value)
    value = HTML_TAG_RE.sub("", value)
    return SPACE_RE.sub(" ", html.unescape(value)).strip()


def _expand_quran_range(chapter: int, start: int, end: int | None) -> list[str]:
    end = end or start
    if not 1 <= chapter <= 114 or not 1 <= start <= end or end - start > 20:
        return []
    return [f"{chapter}:{verse}" for verse in range(start, end + 1)]


def detect_numeric_quran_references(value: str) -> set[str]:
    normalized_digits = normalize_arabic_cues(value)
    references: set[str] = set()
    for match in QURAN_NUMERIC_REF_RE.finditer(normalized_digits):
        prefix = normalized_digits[max(0, match.start() - 40) : match.start()]
        starts_like_citation = prefix.rstrip().endswith(("(", "[", "﴿"))
        has_quran_context = bool(
            re.search(
                r"(?:qur['’]?an|quran|سورة|(?:ال)?اي(?:ة|ات))\s*$",
                prefix,
                re.IGNORECASE,
            )
        )
        if not starts_like_citation and not has_quran_context:
            continue
        references.update(
            _expand_quran_range(
                int(match.group("chapter")),
                int(match.group("start")),
                int(match.group("end")) if match.group("end") else None,
            )
        )
    return references


def detect_hadith_references(value: str) -> list[HadithReference]:
    normalized_digits = normalize_arabic_cues(value)
    references: list[HadithReference] = []
    seen: set[tuple[str, str]] = set()
    suffix = (
        r"\s*(?:[،,:#№-]\s*)?(?:حديث\s*)?(?:رقم\s*)?"
        r"(?:hadith\s*)?(?:no\.?\s*)?\(?\s*(?P<number>\d+[a-z]?)"
    )
    for collection, title, aliases in COLLECTIONS:
        for alias in aliases:
            for match in re.finditer(rf"(?:{alias}){suffix}", normalized_digits, re.IGNORECASE):
                key = (collection, match.group("number"))
                if key not in seen:
                    references.append(HadithReference(collection, title, key[1]))
                    seen.add(key)
    return references[:10]


def _contains_words(haystack: tuple[str, ...], needle: tuple[str, ...]) -> bool:
    if not needle or len(needle) > len(haystack):
        return False
    width = len(needle)
    return any(
        haystack[index : index + width] == needle
        for index in range(len(haystack) - width + 1)
    )


def _longest_common_word_run(left: tuple[str, ...], right: tuple[str, ...]) -> int:
    if not left or not right:
        return 0
    previous = [0] * (len(right) + 1)
    best = 0
    for left_word in left:
        current = [0] * (len(right) + 1)
        for index, right_word in enumerate(right, start=1):
            if left_word == right_word:
                current[index] = previous[index - 1] + 1
                best = max(best, current[index])
        previous = current
    return best


class CanonicalSourceService:
    """Retrieves canonical English wording while keeping all credentials on the backend."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self.settings = settings
        self.client = client
        self._quran_token: str | None = None
        self._quran_token_expires_at = 0.0
        self._quran_verses: dict[str, QuranVerse] | None = None
        self._quran_bigram_index: dict[tuple[str, str], set[str]] = {}
        self._quran_chapters: dict[int, str] = {}

    @property
    def _uses_quran_oauth(self) -> bool:
        return self.settings.quran_api_mode == "oauth"

    def _quran_urls(self) -> tuple[str, str]:
        environment = self.settings.quran_foundation_environment
        if environment == "production":
            return "https://oauth2.quran.foundation", "https://apis.quran.foundation"
        return "https://prelive-oauth2.quran.foundation", "https://apis-prelive.quran.foundation"

    async def _get_quran_token(self, force: bool = False) -> str:
        if (
            not self.settings.quran_foundation_client_id
            or not self.settings.quran_foundation_client_secret
        ):
            raise CanonicalSourceError(
                "Quran Foundation OAuth mode requires both client ID and client secret"
            )
        if (
            not force
            and self._quran_token
            and time.monotonic() < self._quran_token_expires_at
        ):
            return self._quran_token
        auth_base, _ = self._quran_urls()
        try:
            response = await self.client.post(
                f"{auth_base}/oauth2/token",
                auth=(
                    self.settings.quran_foundation_client_id,
                    self.settings.quran_foundation_client_secret,
                ),
                data={"grant_type": "client_credentials", "scope": "content"},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            payload = response.json()
            token = payload.get("access_token")
            if not isinstance(token, str) or not token:
                raise CanonicalSourceError("Quran Foundation returned no access token")
            expires_in = max(int(payload.get("expires_in", 3600)), 60)
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise CanonicalSourceError("Quran Foundation authentication failed") from exc
        self._quran_token = token
        self._quran_token_expires_at = time.monotonic() + expires_in - 30
        return token

    async def _quran_get(self, path: str, params: dict[str, str] | None = None) -> dict:
        if not self._uses_quran_oauth:
            url = f"{self.settings.quran_legacy_api_base_url.rstrip('/')}/{path.lstrip('/')}"
            try:
                response = await self.client.get(url, params=params)
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise CanonicalSourceError("Quran.com content request failed") from exc

        _, api_base = self._quran_urls()
        url = f"{api_base}/content/api/v4/{path.lstrip('/')}"
        for attempt in range(2):
            token = await self._get_quran_token(force=attempt == 1)
            try:
                response = await self.client.get(
                    url,
                    params=params,
                    headers={
                        "x-auth-token": token,
                        "x-client-id": self.settings.quran_foundation_client_id or "",
                    },
                )
            except httpx.HTTPError as exc:
                raise CanonicalSourceError("Quran Foundation content request failed") from exc
            if response.status_code == 401 and attempt == 0:
                self._quran_token = None
                continue
            try:
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise CanonicalSourceError("Quran Foundation content request failed") from exc
        raise CanonicalSourceError("Quran Foundation rejected the refreshed access token")

    async def _load_quran_catalog(self) -> dict[str, QuranVerse]:
        if self._quran_verses is not None:
            return self._quran_verses
        verse_result, chapter_result = await asyncio.gather(
            self._quran_get("quran/verses/uthmani"),
            self._quran_get("chapters", {"language": "ar"}),
            return_exceptions=True,
        )
        if isinstance(verse_result, BaseException):
            raise CanonicalSourceError(
                "Quran.com Arabic verse catalog is unavailable"
            ) from verse_result
        verses: dict[str, QuranVerse] = {}
        for item in verse_result.get("verses", []):
            key = item.get("verse_key")
            arabic = item.get("text_uthmani")
            if isinstance(key, str) and isinstance(arabic, str):
                normalized_words = normalize_arabic_words(arabic)
                verses[key] = QuranVerse(key, arabic, normalized_words)
                for index in range(len(normalized_words) - 1):
                    bigram = normalized_words[index : index + 2]
                    self._quran_bigram_index.setdefault(bigram, set()).add(key)
        if not verses:
            raise CanonicalSourceError("Quran.com returned an empty Arabic verse catalog")
        self._quran_verses = verses
        if not isinstance(chapter_result, BaseException):
            for item in chapter_result.get("chapters", []):
                chapter_id = item.get("id")
                name = item.get("name_arabic")
                if isinstance(chapter_id, int) and isinstance(name, str):
                    self._quran_chapters[chapter_id] = name
        return verses

    def _detect_named_quran_references(self, value: str) -> set[str]:
        words = " ".join(normalize_arabic_words(value))
        references: set[str] = set()
        for chapter, name in self._quran_chapters.items():
            normalized_name = " ".join(normalize_arabic_words(name))
            if not normalized_name:
                continue
            pattern = re.compile(
                rf"(?:سورة\s+{re.escape(normalized_name)}\s+(?:(?:ال)?اية\s+)?)"
                rf"|(?:{re.escape(normalized_name)}\s+(?:ال)?اية\s+)"
            )
            for match in pattern.finditer(words):
                remainder = words[match.end() :]
                number = re.match(r"(?P<start>\d{1,3})(?:\s+[-–—]\s+(?P<end>\d{1,3}))?", remainder)
                if number:
                    references.update(
                        _expand_quran_range(
                            chapter,
                            int(number.group("start")),
                            int(number.group("end")) if number.group("end") else None,
                        )
                    )
        return references

    def _detect_quoted_quran_verses(
        self, value: str
    ) -> tuple[set[str], set[str], list[str]]:
        if self._quran_verses is None:
            return set(), set(), []
        sermon_words = normalize_arabic_words(value)
        matches = {
            key
            for key, verse in self._quran_verses.items()
            if len(verse.normalized_words) >= 4
            and _contains_words(sermon_words, verse.normalized_words)
        }
        verbatim_matches = set(matches)
        issues: list[str] = []
        for passage in quran_passage_candidates(value):
            passage_words = normalize_arabic_words(passage.text)
            possible_keys: set[str] = set()
            for index in range(len(passage_words) - 1):
                possible_keys.update(
                    self._quran_bigram_index.get(passage_words[index : index + 2], set())
                )
            scores = {
                key: _longest_common_word_run(passage_words, verse.normalized_words)
                for key in possible_keys
                if (verse := self._quran_verses.get(key)) is not None
            }
            best_score = max(scores.values(), default=0)
            if best_score < passage.minimum_match_words:
                continue
            best_keys = {key for key, score in scores.items() if score == best_score}
            if best_keys == {"1:1", "27:30"}:
                best_keys = {"1:1"}
            elif len(best_keys) > 1:
                excerpt = " ".join(passage_words[:8])
                issues.append(
                    f"Qur'an-formatted passage '{excerpt}' matched multiple verses: "
                    + ", ".join(sorted(best_keys))
                )
            matches.update(best_keys)
            verbatim_matches.update(
                key
                for key in best_keys
                if _contains_words(passage_words, self._quran_verses[key].normalized_words)
            )

        # The basmalah occurs inside 27:30 as well as at 1:1. In a sermon opening without an
        # explicit 27:30 reference, present the conventional 1:1 source rather than both.
        if (
            {"1:1", "27:30"}.issubset(matches)
            and "27:30" not in detect_numeric_quran_references(value)
        ):
            matches.remove("27:30")
            verbatim_matches.discard("27:30")
        return matches, verbatim_matches, issues

    async def _quran_translation(self, verse_key: str, verbatim_required: bool) -> RetrievedSource:
        payload = await self._quran_get(
            f"quran/translations/{self.settings.quran_translation_id}",
            {"verse_key": verse_key, "fields": "verse_key,resource_name"},
        )
        translations = payload.get("translations", [])
        item = next(
            (
                candidate
                for candidate in translations
                if candidate.get("verse_key", verse_key) == verse_key
                and isinstance(candidate.get("text"), str)
            ),
            None,
        )
        if item is None:
            raise CanonicalSourceError(f"Quran.com returned no translation for {verse_key}")
        metadata = payload.get("meta", {})
        translation_name = (
            item.get("resource_name")
            or metadata.get("translation_name")
            or f"translation {self.settings.quran_translation_id}"
        )
        return RetrievedSource(
            chunk_id=f"canonical:quran:{verse_key}",
            source_id=f"quran.com:{verse_key}",
            title=f"Qur'an {verse_key} — {translation_name}",
            authority="Quran.com",
            text=_clean_html(item["text"]),
            score=10_000,
            source_kind="quran",
            url=f"https://quran.com/{verse_key.replace(':', '/')}",
            canonical=True,
            verbatim_required=verbatim_required,
        )

    async def _retrieve_quran(self, value: str) -> CanonicalRetrieval:
        issues: list[str] = []
        references = detect_numeric_quran_references(value)
        quoted: set[str] = set()
        verbatim_matches: set[str] = set()
        try:
            verses = await self._load_quran_catalog()
            references.update(self._detect_named_quran_references(value))
            quoted, verbatim_matches, matching_issues = self._detect_quoted_quran_verses(value)
            issues.extend(matching_issues)
            references.update(quoted)
            invalid = {reference for reference in references if reference not in verses}
            if invalid:
                issues.append(
                    "Invalid Qur'an reference(s) detected: " + ", ".join(sorted(invalid))
                )
                references.difference_update(invalid)
        except CanonicalSourceError as exc:
            issues.append(
                f"Quran.com comparison unavailable: {exc}. "
                "Verify any Qur'anic wording before approval."
            )

        if has_quran_cue(value) and not references:
            issues.append(
                "Possible Qur'anic quotation detected without a resolvable verse reference; "
                "verify it on Quran.com before approval."
            )

        async def fetch(reference: str) -> RetrievedSource | Exception:
            try:
                return await self._quran_translation(reference, reference in verbatim_matches)
            except Exception as exc:  # converted to a reviewer-facing issue below
                return exc

        fetched = await asyncio.gather(*(fetch(reference) for reference in sorted(references)))
        sources: list[RetrievedSource] = []
        for reference, result in zip(sorted(references), fetched, strict=True):
            if isinstance(result, Exception):
                issues.append(
                    f"Quran.com translation for {reference} could not be retrieved; "
                    "verify it manually before approval."
                )
            else:
                sources.append(result)
        return CanonicalRetrieval(sources, issues)

    async def _hadith_source(self, reference: HadithReference, value: str) -> RetrievedSource:
        if not self.settings.sunnah_api_key:
            raise CanonicalSourceError("Sunnah.com API key is not configured")
        url = (
            f"{self.settings.sunnah_api_base_url.rstrip('/')}/collections/"
            f"{reference.collection}/hadiths/{reference.hadith_number}"
        )
        try:
            response = await self.client.get(
                url,
                headers={"X-API-Key": self.settings.sunnah_api_key},
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise CanonicalSourceError("Sunnah.com content request failed") from exc
        language_items = payload.get("hadith", [])
        english = next(
            (
                item
                for item in language_items
                if str(item.get("lang", "")).lower().startswith("en")
                and isinstance(item.get("body"), str)
            ),
            None,
        )
        if english is None:
            raise CanonicalSourceError("Sunnah.com returned no English wording for the hadith")
        grades = [
            " — ".join(
                part
                for part in (
                    str(item.get("grade", "")).strip(),
                    str(item.get("graded_by", "")).strip(),
                )
                if part
            )
            for item in english.get("grades", [])
            if isinstance(item, dict)
        ]
        grade_suffix = f" — {', '.join(grade for grade in grades if grade)}" if grades else ""
        arabic = next(
            (
                item
                for item in language_items
                if str(item.get("lang", "")).lower().startswith("ar")
                and isinstance(item.get("body"), str)
            ),
            None,
        )
        verbatim_required = False
        if arabic is not None:
            arabic_words = normalize_arabic_words(_clean_html(arabic["body"]))
            verbatim_required = len(arabic_words) >= 3 and _contains_words(
                normalize_arabic_words(value), arabic_words
            )
        return RetrievedSource(
            chunk_id=(
                f"canonical:sunnah:{reference.collection}:{reference.hadith_number}"
            ),
            source_id=f"sunnah.com:{reference.collection}:{reference.hadith_number}",
            title=f"{reference.collection_title} {reference.hadith_number}{grade_suffix}",
            authority="Sunnah.com",
            text=_clean_html(english["body"]),
            score=10_000,
            source_kind="hadith",
            url=f"https://sunnah.com/{reference.collection}:{reference.hadith_number}",
            canonical=True,
            verbatim_required=verbatim_required,
        )

    async def _retrieve_hadith(self, value: str) -> CanonicalRetrieval:
        references = detect_hadith_references(value)
        issues: list[str] = []
        passages = hadith_passage_candidates(value)
        if has_hadith_cue(value) and not references:
            excerpt = ""
            if passages:
                excerpt_words = passages[0].text.split()
                excerpt = f" Detected passage: {' '.join(excerpt_words[:18])}."
            issues.append(
                "Possible hadith quotation detected without an exact collection and number; "
                f"add or verify its Sunnah.com reference before approval.{excerpt}"
            )

        async def fetch(reference: HadithReference) -> RetrievedSource | Exception:
            try:
                return await self._hadith_source(reference, value)
            except Exception as exc:  # converted to a reviewer-facing issue below
                return exc

        fetched = await asyncio.gather(*(fetch(reference) for reference in references))
        sources: list[RetrievedSource] = []
        for reference, result in zip(references, fetched, strict=True):
            if isinstance(result, Exception):
                issues.append(
                    f"Sunnah.com wording for {reference.collection_title} "
                    f"{reference.hadith_number} could not be retrieved: {result}. "
                    "Verify it manually before approval."
                )
            else:
                sources.append(result)
        return CanonicalRetrieval(sources, issues)

    async def retrieve(self, value: str) -> CanonicalRetrieval:
        if not self.settings.canonical_sources_enabled:
            return CanonicalRetrieval([], [])
        quran, hadith = await asyncio.gather(
            self._retrieve_quran(value),
            self._retrieve_hadith(value),
        )
        sources = quran.sources + hadith.sources
        sources.sort(key=lambda source: (source.source_kind, source.chunk_id))
        return CanonicalRetrieval(sources, list(dict.fromkeys(quran.issues + hadith.issues)))
