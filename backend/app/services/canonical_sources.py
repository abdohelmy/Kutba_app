import asyncio
import html
import math
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass, replace

import httpx

from app.core.config import Settings
from app.services.retrieval import RetrievedSource, SourceOccurrence

ARABIC_MARKS_RE = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
ARABIC_WORD_RE = re.compile(r"[\u0621-\u063A\u0641-\u064A0-9]+")
ARABIC_SOURCE_TOKEN_RE = re.compile(
    r"(?:[\u0621-\u063A\u0641-\u064A\u0671][\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]*)+"
)
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
QURAN_SPEECH_CUE_RE = re.compile(r"قال\s+(?:الله(?:\s+تعالي)?|تعالي|سبحانه(?:\s+وتعالي)?|عز\s+وجل)")
QURAN_VERSE_MARKER_RE = re.compile(
    r"(?:"
    r"\(\s*[0-9٠-٩۰-۹]{1,3}\s*\)|"
    r"\[\s*[0-9٠-٩۰-۹]{1,3}\s*\]|"
    r"\{\s*[0-9٠-٩۰-۹]{1,3}\s*\}|"
    r"（\s*[0-9٠-٩۰-۹]{1,3}\s*）|"
    r"【\s*[0-9٠-٩۰-۹]{1,3}\s*】"
    r")"
)
HADITH_CUE_RE = re.compile(
    r"(?:في\s+الحديث|قال\s+(?:رسول\s+الله|النبي)|عن\s+(?:رسول\s+الله|النبي)|"
    r"رواه\s+(?:البخاري|مسلم|النسائي|ابو\s+داود|ابي\s+داود|الترمذي|ابن\s+ماجه)|"
    r"صلي\s+الله\s+عليه\s+وسلم|صلعم)",
    re.IGNORECASE,
)
HADITH_SPEECH_CUE_RE = re.compile(
    r"(?:في\s+الحديث|قال\s+(?:رسول\s+الله|النبي)|عن\s+(?:رسول\s+الله|النبي)|"
    r"صلي\s+الله\s+عليه\s+وسلم|صلعم)",
    re.IGNORECASE,
)
HADITH_WEB_ATTRIBUTION_RE = re.compile(
    r"قال\s+رسول\s+الله(?:\s+صلي\s+الله\s+عليه\s+وسلم)?",
    re.IGNORECASE,
)
REFERENCE_ONLY_RE = re.compile(
    r"^(?:رواه|اخرجه|صححه|حسنه|ضعفه|متفق\s+عليه|حديث\s+(?:رقم|number))\b",
    re.IGNORECASE,
)
HADITH_ATTRIBUTED_PASSAGE_RE = re.compile(
    r"(?:"
    r"قال\s+(?:رسول\s+الله|النبي)(?:\s+صلى\s+الله\s+عليه\s+وسلم)?|"
    r"فقال(?:\s+عليه\s+الصلاة\s+والسلام)?|"
    r"قال\s+عليه\s+الصلاة\s+والسلام"
    r")\s*[:：]\s*[«“❝‹「『\"]*"
    r"(?P<text>.*?)"
    r"(?=(?:[»”❞›」』]+|\[\s*رواه|$))",
    re.DOTALL,
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
    start: int | None = None
    end: int | None = None


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
    words = ARABIC_WORD_RE.findall(value.lower())
    # Uthmani script omits some internal alifs that modern sermon spelling supplies. Limit the
    # comparison skeleton to longer definite words; globally deleting alif makes short words such
    # as قال and قل collide and produced unsafe source matches.
    return tuple(
        f"ال{word[2:].replace('ا', '')}" if len(word) >= 5 and word.startswith("ال") else word
        for word in words
    )


def normalize_arabic_cues(value: str) -> str:
    value = value.replace("ﷺ", " صلى الله عليه وسلم ")
    value = value.replace("ؐ", " صلى الله عليه وسلم ")
    value = value.replace("ﷴ", " رسول الله ")
    value = value.translate(DIGIT_TRANSLATION)
    value = ARABIC_MARKS_RE.sub("", value)
    return SPACE_RE.sub(" ", value.translate(ARABIC_CHARACTER_TRANSLATION)).strip().lower()


def passage_match_minimum(passage: PassageCandidate | str) -> int:
    """Scale evidence requirements for long passages while preserving short quotations."""
    text = passage.text if isinstance(passage, PassageCandidate) else passage
    supplied_minimum = passage.minimum_match_words if isinstance(passage, PassageCandidate) else 3
    word_count = len(normalize_arabic_words(text))
    return min(word_count, 8, max(supplied_minimum, (word_count + 1) // 2))


def arabic_word_overlap(left: str, right: str) -> float:
    """Ordered word coverage of the sermon passage by a candidate canonical source."""
    left_words = normalize_arabic_words(left)
    right_words = normalize_arabic_words(right)
    if not left_words or not right_words:
        return 0.0
    return _longest_common_word_subsequence(left_words, right_words) / len(left_words)


def hadith_passages_match(left: str, right: str, minimum_ratio: float = 0.70) -> bool:
    left_words = normalize_arabic_words(left)
    if len(left_words) < 3:
        return False
    return arabic_word_overlap(left, right) >= minimum_ratio


def hadith_search_excerpt(value: str) -> str:
    """Use at most the first three sentences and first 15 words for Sunnah.com search."""
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?:\r?\n+|(?<=[.!?؟؛])\s+)", value.strip())
        if sentence.strip()
    ][:3]
    words = re.findall(r"\S+", " ".join(sentences))
    return " ".join(words[:15])


def has_quran_cue(value: str) -> bool:
    return bool(QURAN_CUE_RE.search(normalize_arabic_cues(value)))


def has_hadith_cue(value: str) -> bool:
    return bool(HADITH_CUE_RE.search(normalize_arabic_cues(value)))


def _deduplicate_passages(passages: list[PassageCandidate]) -> list[PassageCandidate]:
    unique: list[PassageCandidate] = []
    normalized_unique: list[tuple[tuple[str, ...], int | None, int | None]] = []
    for passage in passages:
        normalized = normalize_arabic_words(passage.text)
        if len(normalized) < passage.minimum_match_words:
            continue
        if REFERENCE_ONLY_RE.search(normalize_arabic_cues(passage.text)):
            continue
        occurrence_key = (normalized, passage.start, passage.end)
        if occurrence_key in normalized_unique:
            continue
        # Cues and tashkeel can yield a whole surrounding sentence after a tighter quoted or
        # attributed candidate has already been found. Avoid searching the same quotation twice.
        if passage.reason in {"hadith cue", "Qur'an cue", "tashkil"} and any(
            len(existing) >= passage.minimum_match_words
            and (_contains_words(normalized, existing) or _contains_words(existing, normalized))
            for existing, _start, _end in normalized_unique
        ):
            continue
        unique.append(passage)
        normalized_unique.append(occurrence_key)
    return unique


def bounded_passage_candidates(
    value: str, *, split_sentences: bool = True
) -> list[PassageCandidate]:
    """Return Arabic text enclosed by common quotation or bracket pairs."""
    patterns = (
        (re.compile(r"﴿(?P<text>[^﴾]{2,4000})﴾", re.DOTALL), 2, "Qur'an brackets"),
        (re.compile(r"«(?P<text>[^»]{2,4000})»", re.DOTALL), 3, "quotation marks"),
        (re.compile(r"“(?P<text>[^”]{2,4000})”", re.DOTALL), 3, "quotation marks"),
        (re.compile(r"‘(?P<text>[^’]{2,4000})’", re.DOTALL), 3, "quotation marks"),
        (re.compile(r"❝(?P<text>[^❞]{2,4000})❞", re.DOTALL), 3, "quotation marks"),
        (re.compile(r"‹(?P<text>[^›]{2,4000})›", re.DOTALL), 3, "quotation marks"),
        (re.compile(r"「(?P<text>[^」]{2,4000})」", re.DOTALL), 3, "quotation marks"),
        (re.compile(r"『(?P<text>[^』]{2,4000})』", re.DOTALL), 3, "quotation marks"),
        (re.compile(r"《(?P<text>[^》]{2,4000})》", re.DOTALL), 3, "quotation marks"),
        (re.compile(r"〈(?P<text>[^〉]{2,4000})〉", re.DOTALL), 3, "quotation marks"),
        (re.compile(r'"(?P<text>[^"\n]{2,4000})"'), 3, "quotation marks"),
        (
            re.compile(r"(?<!\w)'(?P<text>[^'\n]{2,4000})'(?!\w)"),
            3,
            "quotation marks",
        ),
        (re.compile(r"\((?P<text>[^()]{2,4000})\)", re.DOTALL), 3, "round brackets"),
        (re.compile(r"\[(?P<text>[^\[\]]{2,4000})\]", re.DOTALL), 3, "square brackets"),
        (re.compile(r"\{(?P<text>[^{}]{2,4000})\}", re.DOTALL), 3, "curly brackets"),
        (re.compile(r"（(?P<text>[^（）]{2,4000})）", re.DOTALL), 3, "round brackets"),
        (re.compile(r"【(?P<text>[^【】]{2,4000})】", re.DOTALL), 3, "square brackets"),
        (re.compile(r"〔(?P<text>[^〔〕]{2,4000})〕", re.DOTALL), 3, "square brackets"),
    )
    passages: list[PassageCandidate] = []
    for pattern, minimum, reason in patterns:
        for match in pattern.finditer(value):
            raw_text = match.group("text")
            text = raw_text.strip()
            text_offset = match.start("text") + len(raw_text) - len(raw_text.lstrip())
            sentences = (
                [
                    sentence.strip()
                    for sentence in re.split(r"(?:\r?\n+|(?<=[.!?؟])\s+)", text)
                    if sentence.strip()
                ]
                if split_sentences
                else [text]
            )
            qualifying_sentences = [
                sentence
                for sentence in sentences
                if len(normalize_arabic_words(sentence)) >= minimum
            ]
            if len(qualifying_sentences) > 1:
                cursor = 0
                for sentence in qualifying_sentences:
                    relative_start = raw_text.find(sentence, cursor)
                    if relative_start < 0:
                        passages.append(PassageCandidate(sentence, minimum, reason))
                        continue
                    absolute_start = match.start("text") + relative_start
                    passages.append(
                        PassageCandidate(
                            sentence,
                            minimum,
                            reason,
                            absolute_start,
                            absolute_start + len(sentence),
                        )
                    )
                    cursor = relative_start + len(sentence)
            else:
                passages.append(
                    PassageCandidate(
                        text,
                        minimum,
                        reason,
                        text_offset,
                        text_offset + len(text),
                    )
                )
    return passages


def _cue_passages(value: str, cue: re.Pattern[str], reason: str) -> list[PassageCandidate]:
    normalized = normalize_arabic_cues(value)
    passages: list[PassageCandidate] = []
    for match in cue.finditer(normalized):
        remainder = normalized[match.end() :].lstrip(" :：،,-–—")
        candidate = re.split(r"[\n\r.;؛]", remainder, maxsplit=1)[0].strip()
        candidate = candidate.strip(' \t:：،,-–—«»“”❝❞‹›「」『』"﴿﴾')
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


def _hadith_attributed_passages(value: str) -> list[PassageCandidate]:
    normalized = normalize_arabic_cues(value)
    return [
        PassageCandidate(match.group("text").strip(), 3, "hadith attribution")
        for match in HADITH_ATTRIBUTED_PASSAGE_RE.finditer(normalized)
        if match.group("text").strip()
    ]


def _split_numbered_quran_passage(passage: PassageCandidate) -> list[PassageCandidate]:
    """Split a bounded multi-verse quotation at isolated parenthesized verse numbers."""
    markers = list(QURAN_VERSE_MARKER_RE.finditer(passage.text))
    if not markers:
        return [passage]

    fragments: list[PassageCandidate] = []
    cursor = 0
    for marker in (*markers, None):
        fragment_end = marker.start() if marker is not None else len(passage.text)
        raw_fragment = passage.text[cursor:fragment_end]
        text = raw_fragment.strip(" \t\r\n:：،,؛;.-–—")
        if len(normalize_arabic_words(text)) >= 2:
            leading_trim = len(raw_fragment) - len(raw_fragment.lstrip(" \t\r\n:：،,؛;.-–—"))
            relative_start = cursor + leading_trim
            start = passage.start + relative_start if passage.start is not None else None
            fragments.append(
                PassageCandidate(
                    text=text,
                    minimum_match_words=2,
                    reason="numbered Qur'an verse",
                    start=start,
                    end=start + len(text) if start is not None else None,
                )
            )
        if marker is not None:
            cursor = marker.end()
    return fragments or [passage]


def quran_passage_candidates(value: str) -> list[PassageCandidate]:
    bounded = bounded_passage_candidates(value)
    passages: list[PassageCandidate] = []
    for passage in bounded:
        marker_count = len(QURAN_VERSE_MARKER_RE.findall(passage.text))
        if marker_count >= 2 or (marker_count == 1 and has_quran_cue(value)):
            passages.extend(_split_numbered_quran_passage(passage))
        else:
            passages.append(passage)
    passages.extend(_cue_passages(value, QURAN_SPEECH_CUE_RE, "Qur'an cue"))
    passages.extend(_vocalized_passages(value))
    return _deduplicate_passages(passages)


def hadith_passage_candidates(value: str) -> list[PassageCandidate]:
    passages = _hadith_attributed_passages(value)
    passages.extend(bounded_passage_candidates(value))
    passages.extend(_cue_passages(value, HADITH_SPEECH_CUE_RE, "hadith cue"))
    passages.extend(_vocalized_passages(value))
    return _deduplicate_passages(passages)


def hadith_web_search_candidates(value: str) -> list[PassageCandidate]:
    """Return whole bounded blocks plus unquoted text attributed to Allah's Messenger."""
    passages = bounded_passage_candidates(value, split_sentences=False)
    passages.extend(_cue_passages(value, HADITH_WEB_ATTRIBUTION_RE, "hadith cue"))
    return _deduplicate_passages(passages)


def hadith_search_passage(value: str) -> str | None:
    """Return a bounded likely hadith passage from cues, honorifics, or quotation marks."""
    passages = hadith_passage_candidates(value)
    if has_hadith_cue(value):
        priority = {
            "hadith attribution": 0,
            "quotation marks": 1,
            "hadith cue": 2,
            "tashkil": 3,
        }
        passages.sort(key=lambda passage: priority.get(passage.reason, 2))
        return passages[0].text if passages else None
    bounded = [passage for passage in passages if passage.reason != "tashkil"]
    return bounded[0].text if bounded else None


def _clean_html(value: str) -> str:
    had_footnote = SUP_RE.search(value) is not None
    value = SUP_RE.sub("", value)
    value = HTML_TAG_RE.sub("", value)
    value = SPACE_RE.sub(" ", html.unescape(value)).strip()
    if had_footnote:
        value = re.sub(r"\s+[-–—]\s*$", "", value)
    return value


def _expand_quran_range(chapter: int, start: int, end: int | None) -> list[str]:
    end = end or start
    if not 1 <= chapter <= 114 or not 1 <= start <= end or end - start > 20:
        return []
    return [f"{chapter}:{verse}" for verse in range(start, end + 1)]


def detect_numeric_quran_references(value: str) -> set[str]:
    normalized_digits = normalize_arabic_cues(value)
    references: set[str] = set()
    for match in QURAN_NUMERIC_REF_RE.finditer(normalized_digits):
        prefix = normalized_digits[max(0, match.start() - 80) : match.start()]
        suffix = normalized_digits[match.end() : match.end() + 8]
        has_quran_context = bool(
            re.search(
                r"(?:qur['’]?an|quran|سورة|(?:ال)?اي(?:ة|ات)|"
                r"قال\s+(?:الله|تعالي|سبحانه)|قال\s+عز\s+وجل)"
                r"[^\n\r.!?؟؛]{0,35}$",
                prefix,
                re.IGNORECASE,
            )
        )
        follows_quran_quote = bool(re.search(r"﴾\s*[\[(]?\s*$", prefix))
        quran_bracket_reference = prefix.rstrip().endswith("﴿") and bool(re.match(r"\s*﴾", suffix))
        if not has_quran_context and not follows_quran_quote and not quran_bracket_reference:
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
        haystack[index : index + width] == needle for index in range(len(haystack) - width + 1)
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


def _longest_common_word_subsequence(left: tuple[str, ...], right: tuple[str, ...]) -> int:
    if not left or not right:
        return 0
    previous = [0] * (len(right) + 1)
    for left_word in left:
        current = [0] * (len(right) + 1)
        for index, right_word in enumerate(right, start=1):
            if left_word == right_word:
                current[index] = previous[index - 1] + 1
            else:
                current[index] = max(previous[index], current[index - 1])
        previous = current
    return previous[-1]


def arabic_passages_match(left: str, right: str, minimum_words: int = 3) -> bool:
    """Conservative contiguous-word check used to verify web-search candidates."""
    left_words = normalize_arabic_words(left)
    right_words = normalize_arabic_words(right)
    if minimum_words < 2 or len(left_words) < minimum_words or len(right_words) < minimum_words:
        return False
    return _longest_common_word_run(left_words, right_words) >= minimum_words


def arabic_passage_is_contained(container: str, passage: str) -> bool:
    passage_words = normalize_arabic_words(passage)
    return len(passage_words) >= 3 and _contains_words(
        normalize_arabic_words(container), passage_words
    )


def _arabic_token_spans(value: str) -> list[tuple[str, int, int]]:
    spans: list[tuple[str, int, int]] = []
    for match in ARABIC_SOURCE_TOKEN_RE.finditer(value):
        normalized = normalize_arabic_words(match.group(0))
        if normalized:
            spans.append((normalized[0], match.start(), match.end()))
    return spans


def _find_arabic_occurrences(value: str, passage: str) -> tuple[SourceOccurrence, ...]:
    tokens = _arabic_token_spans(value)
    needle = normalize_arabic_words(passage)
    if not needle or len(needle) > len(tokens):
        return ()
    occurrences: list[SourceOccurrence] = []
    for index in range(len(tokens) - len(needle) + 1):
        if tuple(token for token, _start, _end in tokens[index : index + len(needle)]) != needle:
            continue
        start = tokens[index][1]
        end = tokens[index + len(needle) - 1][2]
        occurrences.append(SourceOccurrence(value[start:end], start, end))
    return tuple(occurrences)


def find_arabic_occurrences(value: str, passage: str) -> tuple[SourceOccurrence, ...]:
    """Return exact source offsets for a passage after safe Arabic normalization."""
    return _find_arabic_occurrences(value, passage)


def _passage_occurrences(value: str, passage: PassageCandidate) -> tuple[SourceOccurrence, ...]:
    if (
        passage.start is not None
        and passage.end is not None
        and 0 <= passage.start < passage.end <= len(value)
    ):
        return (SourceOccurrence(value[passage.start : passage.end], passage.start, passage.end),)
    return _find_arabic_occurrences(value, passage.text)


def _occurrences_overlap(left: SourceOccurrence, right: SourceOccurrence) -> bool:
    return (
        left.start is not None
        and left.end is not None
        and right.start is not None
        and right.end is not None
        and left.start < right.end
        and right.start < left.end
    )


def quran_passage_is_embedded_in_hadith(
    quran_arabic: str | None,
    hadith_arabic_passages: Iterable[str],
) -> bool:
    """True when a Quran excerpt is already contained in a sourced hadith body."""
    return bool(
        quran_arabic
        and any(
            arabic_passage_is_contained(hadith_arabic, quran_arabic)
            for hadith_arabic in hadith_arabic_passages
            if hadith_arabic
        )
    )


def deduplicate_embedded_quran_sources(
    sources: list[RetrievedSource],
) -> list[RetrievedSource]:
    hadith_sources = [source for source in sources if source.source_kind == "hadith"]
    hadith_arabic = [source.arabic_text for source in hadith_sources if source.arabic_text]
    if not hadith_sources:
        return sources
    deduplicated: list[RetrievedSource] = []
    for source in sources:
        if source.source_kind != "quran":
            deduplicated.append(source)
            continue
        if source.occurrences:
            remaining = tuple(
                occurrence
                for occurrence in source.occurrences
                if not any(
                    _occurrences_overlap(occurrence, hadith_occurrence)
                    and arabic_passage_is_contained(
                        hadith_occurrence.arabic_text, occurrence.arabic_text
                    )
                    for hadith in hadith_sources
                    for hadith_occurrence in hadith.occurrences
                )
            )
            if remaining:
                deduplicated.append(replace(source, occurrences=remaining))
            elif not any(hadith.occurrences for hadith in hadith_sources):
                if not quran_passage_is_embedded_in_hadith(source.arabic_text, hadith_arabic):
                    deduplicated.append(source)
            continue
        if not quran_passage_is_embedded_in_hadith(source.arabic_text, hadith_arabic):
            deduplicated.append(source)
    return deduplicated


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
        self._quran_chapter_display_names: dict[int, str] = {}

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
        if not force and self._quran_token and time.monotonic() < self._quran_token_expires_at:
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
                arabic_name = item.get("name_arabic")
                display_name = item.get("name_simple")
                if isinstance(chapter_id, int):
                    if isinstance(arabic_name, str):
                        self._quran_chapters[chapter_id] = arabic_name
                    if isinstance(display_name, str):
                        self._quran_chapter_display_names[chapter_id] = display_name
        return verses

    def _detect_named_quran_references(self, value: str) -> set[str]:
        normalized = normalize_arabic_cues(value)
        references: set[str] = set()
        for chapter, name in self._quran_chapters.items():
            normalized_name = " ".join(normalize_arabic_words(name))
            if not normalized_name:
                continue
            patterns = (
                re.compile(
                    rf"(?:سورة\s+{re.escape(normalized_name)}|"
                    rf"{re.escape(normalized_name)}\s+(?:ال)?اية)"
                    rf"\s*(?:(?:ال)?اية\s*)?[:：]?\s*"
                    rf"(?P<start>\d{{1,3}})(?:\s*[-–—]\s*(?P<end>\d{{1,3}}))?"
                ),
                re.compile(
                    rf"[\[({{﴿]\s*{re.escape(normalized_name)}\s*[:：]\s*"
                    rf"(?P<start>\d{{1,3}})(?:\s*[-–—]\s*(?P<end>\d{{1,3}}))?"
                    rf"\s*[\])}}﴾]"
                ),
            )
            for pattern in patterns:
                for match in pattern.finditer(normalized):
                    references.update(
                        _expand_quran_range(
                            chapter,
                            int(match.group("start")),
                            int(match.group("end")) if match.group("end") else None,
                        )
                    )
        return references

    def _detect_quoted_quran_verses(
        self, value: str
    ) -> tuple[
        set[str],
        set[str],
        dict[str, tuple[SourceOccurrence, ...]],
        dict[str, int],
        list[str],
    ]:
        if self._quran_verses is None:
            return set(), set(), {}, {}, []
        sermon_words = normalize_arabic_words(value)
        matches: set[str] = set()
        occurrences: dict[str, list[SourceOccurrence]] = {}
        minimum_verbatim_words: dict[str, int] = {}
        for key, verse in self._quran_verses.items():
            if len(verse.normalized_words) < 4 or not _contains_words(
                sermon_words, verse.normalized_words
            ):
                continue
            matches.add(key)
            occurrences[key] = list(_find_arabic_occurrences(value, verse.arabic_text))
        verbatim_matches = set(matches)
        issues: list[str] = []
        for passage in quran_passage_candidates(value):
            passage_words = normalize_arabic_words(passage.text)
            required_match_words = passage_match_minimum(passage)
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
            if best_score < required_match_words:
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
                # Ambiguous Arabic must never silently receive an arbitrary canonical wording.
                continue
            matches.update(best_keys)
            passage_occurrences = _passage_occurrences(value, passage)
            for key in best_keys:
                occurrences.setdefault(key, []).extend(passage_occurrences)
                verse_words = self._quran_verses[key].normalized_words
                if not _contains_words(passage_words, verse_words):
                    minimum_verbatim_words[key] = max(
                        minimum_verbatim_words.get(key, 0),
                        max(3, min(8, math.ceil(best_score * 0.75))),
                    )
            verbatim_matches.update(
                key
                for key in best_keys
                if _contains_words(passage_words, self._quran_verses[key].normalized_words)
            )

        # The basmalah occurs inside 27:30 as well as at 1:1. In a sermon opening without an
        # explicit 27:30 reference, present the conventional 1:1 source rather than both.
        if {"1:1", "27:30"}.issubset(matches) and "27:30" not in detect_numeric_quran_references(
            value
        ):
            matches.remove("27:30")
            verbatim_matches.discard("27:30")
            occurrences.pop("27:30", None)
            minimum_verbatim_words.pop("27:30", None)
        normalized_occurrences = {
            key: tuple(
                {
                    (occurrence.start, occurrence.end, occurrence.arabic_text): occurrence
                    for occurrence in verse_occurrences
                }.values()
            )
            for key, verse_occurrences in occurrences.items()
        }
        return (
            matches,
            verbatim_matches,
            normalized_occurrences,
            minimum_verbatim_words,
            issues,
        )

    async def _quran_translation(
        self,
        verse_key: str,
        verbatim_required: bool,
        occurrences: tuple[SourceOccurrence, ...] = (),
        minimum_verbatim_words: int = 0,
    ) -> RetrievedSource:
        translation_result, transliteration_result = await asyncio.gather(
            self._quran_get(
                f"quran/translations/{self.settings.quran_translation_id}",
                {"verse_key": verse_key, "fields": "verse_key,resource_name"},
            ),
            self._quran_get(
                f"quran/translations/{self.settings.quran_transliteration_id}",
                {"verse_key": verse_key, "fields": "verse_key,resource_name"},
            ),
            return_exceptions=True,
        )
        if isinstance(translation_result, BaseException):
            raise translation_result
        payload = translation_result
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
        chapter = int(verse_key.split(":", maxsplit=1)[0])
        chapter_name = self._quran_chapter_display_names.get(chapter)
        display_reference = f"{chapter_name} {verse_key}" if chapter_name else f"Qur'an {verse_key}"
        transliteration: str | None = None
        if not isinstance(transliteration_result, BaseException):
            transliteration_item = next(
                (
                    candidate
                    for candidate in transliteration_result.get("translations", [])
                    if candidate.get("verse_key", verse_key) == verse_key
                    and isinstance(candidate.get("text"), str)
                ),
                None,
            )
            if transliteration_item is not None:
                transliteration = _clean_html(transliteration_item["text"])
        return RetrievedSource(
            chunk_id=f"canonical:quran:{verse_key}",
            source_id=f"quran.com:{verse_key}",
            title=f"{display_reference} — {translation_name}",
            authority="Quran.com",
            text=_clean_html(item["text"]),
            score=10_000,
            source_kind="quran",
            url=f"https://quran.com/{verse_key.replace(':', '/')}",
            canonical=True,
            verbatim_required=verbatim_required,
            arabic_text=(
                self._quran_verses[verse_key].arabic_text
                if self._quran_verses and verse_key in self._quran_verses
                else None
            ),
            transliteration=transliteration,
            display_reference=display_reference,
            occurrences=occurrences,
            minimum_verbatim_words=minimum_verbatim_words,
        )

    async def _retrieve_quran(self, value: str) -> CanonicalRetrieval:
        issues: list[str] = []
        references = detect_numeric_quran_references(value)
        quoted: set[str] = set()
        verbatim_matches: set[str] = set()
        occurrences: dict[str, tuple[SourceOccurrence, ...]] = {}
        minimum_verbatim_words: dict[str, int] = {}
        try:
            verses = await self._load_quran_catalog()
            references.update(self._detect_named_quran_references(value))
            (
                quoted,
                verbatim_matches,
                occurrences,
                minimum_verbatim_words,
                matching_issues,
            ) = self._detect_quoted_quran_verses(value)
            issues.extend(matching_issues)
            references.update(quoted)
            invalid = {reference for reference in references if reference not in verses}
            if invalid:
                issues.append("Invalid Qur'an reference(s) detected: " + ", ".join(sorted(invalid)))
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
                return await self._quran_translation(
                    reference,
                    reference in verbatim_matches,
                    occurrences.get(reference, ()),
                    minimum_verbatim_words.get(reference, 0),
                )
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
                if result.transliteration is None:
                    issues.append(
                        f"Quran.com transliteration for {reference} could not be retrieved; "
                        "verify any generated fallback before approval."
                    )
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
        if arabic is None:
            raise CanonicalSourceError(
                "Sunnah.com returned no Arabic wording to verify the supplied reference"
            )
        canonical_arabic = _clean_html(arabic["body"])
        passages = hadith_passage_candidates(value)
        matching_passages = [
            passage for passage in passages if hadith_passages_match(passage.text, canonical_arabic)
        ]
        if passages and not matching_passages:
            raise CanonicalSourceError(
                "The supplied hadith number does not match the quoted Arabic at 80% overlap"
            )
        occurrences = tuple(
            occurrence
            for passage in matching_passages
            for occurrence in _passage_occurrences(value, passage)
        )
        verbatim_required = arabic_passage_is_contained(value, canonical_arabic)
        partial_word_count = max(
            (len(normalize_arabic_words(passage.text)) for passage in matching_passages),
            default=0,
        )
        return RetrievedSource(
            chunk_id=(f"canonical:sunnah:{reference.collection}:{reference.hadith_number}"),
            source_id=f"sunnah.com:{reference.collection}:{reference.hadith_number}",
            title=f"{reference.collection_title} {reference.hadith_number}{grade_suffix}",
            authority="Sunnah.com",
            text=_clean_html(english["body"]),
            score=10_000,
            source_kind="hadith",
            url=f"https://sunnah.com/{reference.collection}:{reference.hadith_number}",
            canonical=True,
            verbatim_required=verbatim_required,
            arabic_text=canonical_arabic,
            display_reference=f"{reference.collection_title} {reference.hadith_number}",
            occurrences=occurrences,
            minimum_verbatim_words=(
                0
                if verbatim_required or not partial_word_count
                else max(3, min(8, math.ceil(partial_word_count * 0.75)))
            ),
        )

    async def _retrieve_hadith(self, value: str) -> CanonicalRetrieval:
        references = detect_hadith_references(value)
        issues: list[str] = []
        passages = hadith_passage_candidates(value)
        bounded_passages = [passage for passage in passages if passage.reason != "tashkil"]
        if (has_hadith_cue(value) or bounded_passages) and not references:
            excerpt = ""
            detected = bounded_passages or passages
            if detected:
                excerpt_words = detected[0].text.split()
                excerpt = f" Detected passage: {' '.join(excerpt_words[:18])}."
            issues.append(
                "Possible hadith quotation or bounded Arabic quotation detected without an "
                "exact collection and number; determine whether it is a hadith or Qur'an verse, "
                f"then add or verify its canonical reference before approval.{excerpt}"
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

    async def retrieve_hadith(self, value: str) -> CanonicalRetrieval:
        if not self.settings.canonical_sources_enabled:
            return CanonicalRetrieval([], [])
        return await self._retrieve_hadith(value)

    async def retrieve_quran(self, value: str) -> CanonicalRetrieval:
        if not self.settings.canonical_sources_enabled:
            return CanonicalRetrieval([], [])
        return await self._retrieve_quran(value)

    async def retrieve(self, value: str) -> CanonicalRetrieval:
        if not self.settings.canonical_sources_enabled:
            return CanonicalRetrieval([], [])
        # Preserve the classification order used by translation jobs: hadith first, then Qur'an.
        hadith = await self._retrieve_hadith(value)
        quran = await self._retrieve_quran(value)
        if quran.sources and not has_hadith_cue(value):
            bounded = [
                passage
                for passage in hadith_passage_candidates(value)
                if passage.reason != "tashkil"
            ]
            all_bounded_passages_are_quran = bool(bounded) and all(
                any(
                    source.arabic_text
                    and arabic_passages_match(
                        passage.text,
                        source.arabic_text,
                        minimum_words=passage.minimum_match_words,
                    )
                    for source in quran.sources
                )
                for passage in bounded
            )
            if all_bounded_passages_are_quran:
                hadith = CanonicalRetrieval(
                    hadith.sources,
                    [
                        issue
                        for issue in hadith.issues
                        if not issue.startswith(
                            "Possible hadith quotation or bounded Arabic quotation"
                        )
                    ],
                )
        sources = deduplicate_embedded_quran_sources(quran.sources + hadith.sources)
        sources.sort(key=lambda source: (source.source_kind, source.chunk_id))
        return CanonicalRetrieval(sources, list(dict.fromkeys(quran.issues + hadith.issues)))
