import csv
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings

ARABIC_MARKS = r"\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED"
ARABIC_BASES = r"\u0621-\u063A\u0641-\u064A\u0671"
ARABIC_CHARACTERS = rf"{ARABIC_BASES}{ARABIC_MARKS}\u0750-\u077f\u08a0-\u08ff"
ARABIC_MARKS_RE = re.compile(rf"[{ARABIC_MARKS}]")
ARABIC_TOKEN_RE = re.compile(rf"(?:[{ARABIC_BASES}][{ARABIC_MARKS}]*)+")
ARABIC_LETTER_WITH_MARKS_RE = re.compile(rf"([{ARABIC_BASES}])([{ARABIC_MARKS}]*)")
ARABIC_RUN_RE = re.compile(rf"[{ARABIC_CHARACTERS}]+(?:\s+[{ARABIC_CHARACTERS}]+)*")
PARENTHETICAL_RE = re.compile(rf"\((?P<arabic>[{ARABIC_CHARACTERS}\s]+)\)")
ENGLISH_WORD_RE = re.compile(r"[A-Za-z][A-Za-z’'\-]*")
ENGLISH_CLAUSE_BOUNDARY_RE = re.compile(r"(?:\r?\n+|[.!?;:…]+(?:[\"”’')\]]+)?)")
ENGLISH_QUOTED_PHRASE_RE = re.compile(r"[\"“](?P<phrase>[^\"”]+)[\"”]")
VARIATION_RE = re.compile(
    r"^(?P<arabic>.*?)\s*(?:\((?P<label>[^()]*)\))?\s*—\s*(?P<translation>.+)$"
)
ARABIC_CHARACTER_TRANSLATION = str.maketrans(
    {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ٱ": "ا",
        "ؤ": "و",
        "ئ": "ي",
        "ـ": "",
    }
)
COMMON_PREFIXES = ("و", "ف", "ب", "ك", "ل")
# This rendering was explicitly requested for taqwa; the supplied CSV only lists
# the narrower literal words "fear; piety".
REVIEWED_ENGLISH_RENDERINGS = {
    "التقوى": ("God-consciousness",),
    "ضيق الصدر": ("tightness of chest", "tightness of the chest"),
}
REVIEWED_FORM_RENDERINGS = {("اتقى",): ("guarded against",)}
# Display-only aliases: take the spelling from the sermon, never substitute these
# words into the translation or use them to authorize a different glossary sense.
POPUP_RENDERINGS = {
    "النفس": ("self",), "القضاء": ("divine decree",),
    "القدر": ("measured apportionment",), "السراء": ("prosperity",),
    "الضراء": ("adversity",), "الأجل": ("appointed terms",),
    "السبب": ("means of safety",), "الجنة": ("Paradise",),
    "النار": ("Hell",), "النعيم": ("bliss",),
    "الذكر": ("remembrance of Allah",), "الكفران": ("ingratitude for blessings",),
    "الفتنة": ("trials",), "دار السلام": ("Abode of Peace",),
    "الجزاء": ("recompense",), "جزاء": ("recompense",),
    "الإله": ("deity",), "إله": ("deity",),
    "الزهد": ("most detached",), "الإمام": ("Imam",),
    "المعروف": ("recognized good",),
}
# Explicit renderings for divine-name entries in the supplied catalog. These are
# not ordinary adjective/verb aliases and must never inherit the CSV variations.
DIVINE_NAME_RENDERINGS = {
    "الرحمن": "the Most Compassionate; the Entirely Merciful; the Compassionate",
    "الرحيم": "the Most Merciful; the Especially Merciful; the Merciful",
    "الغفور": "the Oft-Forgiving; the All-Forgiving",
    "الغفار": "the Ever-Forgiving; the Constantly Forgiving",
    "العفو": "the Pardoning; the Ever-Pardoning",
    "التواب": "the Accepter of Repentance; the Accepting of Repentance",
    "الرؤوف": "the Most Kind; the Most Compassionate",
    "الودود": "the Most Loving; the All-Loving",
    "اللطيف": "the Subtly Kind; the Most Subtle; the Most Gentle",
    "الخبير": "the All-Aware; the All Acquainted",
    "العليم": "the All-Knowing; the All Knowing",
    "الحكيم": "the All-Wise; the Perfectly Wise",
    "الحليم": "the Forbearing; the Most Forbearing",
    "الكريم": "the Most Generous; the Generous",
    "الأكرم": "the Most Generous; the Most Noble",
    "الوهاب": "the Bestower; the Ever-Giving",
    "الرزاق": "the Provider; the All-Provider",
    "الفتاح": "the Opener; the Supreme Judge",
    "النصير": "the Helper; the Protector",
    "الولي": "the Protecting Ally; the Protecting Guardian",
    "المولى": "the Protector; the Patron; the Master",
    "الوكيل": "the Trustee; the Disposer of Affairs",
    "الحفيظ": "the Preserver; the Guardian",
    "الرقيب": "the Watchful; the Ever-Watchful",
    "الحسيب": "the Reckoner; the All-Sufficient",
    "الشهيد": "the Witness; the All-Witnessing",
    "المقيت": "the Sustainer",
    "القادر": "the All-Powerful; the Fully Capable",
    "القدير": "the All-Powerful; the Omnipotent",
    "المقتدر": "the Supremely Powerful; the Omnipotent",
    "القوي": "the All-Strong; the Most Strong",
    "المتين": "the Firm; the Unfailing in Strength",
    "الجبار": "the Compeller; the Irresistible",
    "المتكبر": "the Supremely Great; the Supreme",
    "الكبير": "the Most Great; the Incomparably Great",
    "العظيم": "the Magnificent; the Most Great; the Almighty",
    "العلي": "the Most High; the Most High One; the All-High; the Exalted",
    "المتعال": "the Supremely Exalted; the Most Exalted",
    "القدوس": "the Most Holy; the Holy",
    "السلام": "the Source of Peace; the Perfection",
    "المؤمن": "the Giver of Security; the Granter of Security",
    "المهيمن": "the Overseer; the Supreme Guardian",
    "الواحد": "the One; the Only One",
    "الأحد": "the Unique One; the Uniquely One",
    "الصمد": "the Eternal Refuge; the Self-Sufficient; the Eternal",
}
# Corrections to the bundled glossary, without rewriting the uploaded source CSV.
# Huda (guidance) and hady (conduct or a pilgrimage offering) are distinct words.
BUILTIN_CORRECTIONS = {
    "الهدى": {
        "Literal translation": "guidance; right guidance",
    },
    "الهدي": {
        "Meaning": (
            "The intended meaning depends on context. In descriptions of the Prophet's "
            "hady it means his way, conduct, or example. In Hajj and Umrah it means an "
            "animal offered in sacrifice. It is distinct from الهُدى (guidance)."
        ),
        "Literal translation": "prophetic example; way of conduct; sacrificial offering",
        "Alternative context meaning(s)": (
            "Prophetic conduct or example; an animal offering in pilgrimage. "
            "Do not infer the pilgrimage meaning from the English word guidance."
        ),
    },
}
ENGLISH_CONNECTORS = {
    "a",
    "against",
    "an",
    "and",
    "as",
    "at",
    "away",
    "by",
    "for",
    "from",
    "in",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "upon",
    "who",
    "which",
    "with",
}
SUPPLEMENTAL_GLOSSARY_ROWS = (
    {
        "Arabic term": "السلام", "Sense": "ordinary",
        "Literal translation": "peace; salutation; greeting of peace",
        "Meaning": ("Peace, safety, or a greeting wishing peace, according to the sentence. "
                    "This ordinary usage is distinct from As-Salam when used as a name for Allah."),
    },
    {
        "Arabic term": "المؤمن", "Sense": "ordinary",
        "Literal translation": "believer; faithful believer",
        "Meaning": ("A person who has faith in Allah. This human usage is distinct from "
                    "Al-Mu'min when used of Allah, the Giver of Security."),
    },
    {
        "Arabic term": "الآجال",
        "Literal translation": "appointed terms; lifespans",
        "Meaning": ("The appointed times or limits of lives or events. It is the plural of ajal; "
                    "the surrounding sentence identifies what has an appointed term."),
    },
    {
        "Arabic term": "الحديث القدسي",
        "Literal translation": "sacred hadith; hadith qudsi",
        "Meaning": ("A report in which the Prophet relates a statement from Allah. "
                    "It is not a verse of the Qur'an. Calling a report qudsi does not "
                    "by itself establish its authenticity."),
    },
    {
        "Arabic term": "سند حسن",
        "Literal translation": "hasan chain of transmission; good chain of transmission",
        "Meaning": ("A chain of narrators graded hasan (good) by a hadith scholar. "
                    "This explains the grade stated in the sermon; "
                    "it is not a new authentication of the report."),
    },
    {
        "Arabic term": "سند صحيح",
        "Literal translation": "authentic chain of transmission; sound chain of transmission",
        "Meaning": ("A chain of narrators graded sahih (sound or authentic) by a hadith scholar. "
                    "This explains the stated chain assessment, "
                    "not an independent verdict on every version of the report."),
    },
    {
        "Arabic term": "معية الله",
        "Literal translation": "Allah's accompanying presence; Allah's being with His servants",
        "Meaning": ("Allah's being with His servants, understood in the context of the passage. "
                    "In the reassurance to Moses and Aaron in Qur'an 20:46, "
                    "Allah says that He is with them, hearing and seeing."),
    },
    {
        "Arabic term": "أهل الذكر",
        "Literal translation": ("people of the Reminder and knowledge; "
                                "people of knowledge; people of the message"),
        "Meaning": ("Those who possess knowledge of the message or revelation. "
                    "Qur'an 16:43 directs those who do not know to ask them; "
                    "in the sermon's advice this refers to consulting knowledgeable people."),
    },
    {
        "Arabic term": "الضنك",
        "Meaning": (
            "Severe constriction, distress, and hardship that makes life feel narrow and "
            "burdensome. In Qur'anic context it describes a deeply difficult life, not only "
            "financial poverty."
        ),
        "Literal translation": "distress; severe constriction; hardship",
        "Arabic variations + translation": (
            "الضَّنْك (vocalized noun) — distress; severe constriction | "
            "ضَنكًا (indefinite accusative) — a depressed [i.e., difficult] life"
        ),
        "Alternative context meaning(s)": "",
    },
    {
        "Arabic term": "سنة الله",
        "Meaning": (
            "Allah's established and consistent way in creation, guidance, and the "
            "consequences of human conduct. It means a divine pattern or law, not the "
            "Prophetic Sunnah."
        ),
        "Literal translation": "Allah's established way; divine pattern",
        "Arabic variations + translation": (
            "سُنَّةُ اللَّه (vocalized phrase) — Allah's established way; divine pattern | "
            "سنه الله (common OCR variation) — Allah's established way; divine pattern"
        ),
        "Alternative context meaning(s)": "",
    },
)


@dataclass(frozen=True)
class GlossaryForm:
    arabic_term: str
    translation: str
    grammatical_label: str | None
    normalized_words: tuple[str, ...]
    vocalized_words: tuple[str, ...]
    has_tashkeel: bool


@dataclass(frozen=True)
class GlossaryEntry:
    arabic_term: str
    meaning: str
    literal_translation: str
    normalized_words: tuple[str, ...]
    vocalized_words: tuple[str, ...]
    has_tashkeel: bool
    forms: tuple[GlossaryForm, ...]
    alternative_context_meanings: str = ""
    is_divine_name: bool = False

    @property
    def key(self) -> str:
        return f"{self.arabic_term}\u0000{self.meaning}"


@dataclass(frozen=True)
class GlossaryHit:
    entry: GlossaryEntry
    form: GlossaryForm
    position: int
    order: int
    specific_vocalization: bool
    alignment_cost: int


@dataclass(frozen=True)
class GlossaryMatch:
    entry: GlossaryEntry
    display_term: str
    arabic_term: str
    literal_translation: str
    translation_start: int | None = None
    translation_end: int | None = None
    english_phrase: str = ""


@dataclass(frozen=True)
class ArabicToken:
    normalized: str
    vocalized: str
    has_tashkeel: bool


@dataclass(frozen=True)
class ArabicWordAlignment:
    actual_prefix_bases: int
    expected_prefix_bases: int


def _row_value(row: dict[str, str | None], name: str) -> str:
    return (row.get(name) or "").strip()


def _normalized_arabic(value: str, preserve_tashkeel: bool) -> tuple[str, ...]:
    value = value.translate(ARABIC_CHARACTER_TRANSLATION)
    value = unicodedata.normalize("NFD", value)
    if not preserve_tashkeel:
        value = ARABIC_MARKS_RE.sub("", value)
    return tuple(match.group(0) for match in ARABIC_TOKEN_RE.finditer(value))


@lru_cache(maxsize=2048)
def _divine_name_rendering(value: str) -> str | None:
    normalized = _normalized_arabic(value, False)
    return next((rendering for name, rendering in DIVINE_NAME_RENDERINGS.items()
                 if _normalized_arabic(name, False) == normalized), None)


def _make_form(
    arabic_term: str,
    translation: str,
    grammatical_label: str | None = None,
) -> GlossaryForm | None:
    normalized_words = _normalized_arabic(arabic_term, preserve_tashkeel=False)
    if not normalized_words:
        return None
    vocalized_words = _normalized_arabic(arabic_term, preserve_tashkeel=True)
    return GlossaryForm(
        arabic_term=arabic_term.strip(),
        translation=translation.strip(),
        grammatical_label=grammatical_label.strip() if grammatical_label else None,
        normalized_words=normalized_words,
        vocalized_words=vocalized_words,
        has_tashkeel=bool(ARABIC_MARKS_RE.search(arabic_term)),
    )


def _parse_variations(value: str) -> tuple[GlossaryForm, ...]:
    forms: list[GlossaryForm] = []
    for item in value.split("|"):
        item = item.strip()
        if not item:
            continue
        match = VARIATION_RE.fullmatch(item)
        if match is None:
            continue
        form = _make_form(
            match.group("arabic"),
            match.group("translation"),
            match.group("label"),
        )
        if form is not None:
            forms.append(form)
    return tuple(forms)


def normalized_arabic_key(value: str) -> str:
    """Stable database key for a mosque-owned Arabic term."""
    # Preserve existing database identifiers; lexical matching itself keeps ى and ي distinct.
    return " ".join(_normalized_arabic(value.replace("ى", "ي"), preserve_tashkeel=False))


def build_glossary_entry(
    arabic_term: str,
    meaning: str,
    literal_translation: str,
    arabic_variations: str = "",
    alternative_context_meanings: str = "",
    is_divine_name: bool = False,
) -> GlossaryEntry:
    # Preserve ordinary mosque-defined senses (e.g. believer for المؤمن).
    # Explicitly divine descriptions also opt into the safer name matching.
    is_divine_name = is_divine_name or bool(
        _divine_name_rendering(arabic_term)
        and re.search(r"\b(?:divine name|Allah's name|name of Allah)\b", meaning, re.IGNORECASE)
    )
    divine_rendering = _divine_name_rendering(arabic_term) if is_divine_name else None
    if divine_rendering:
        literal_translation = divine_rendering
        arabic_variations = ""
    canonical = _make_form(arabic_term, literal_translation)
    if canonical is None:
        raise ValueError("Arabic term must contain at least one Arabic word")
    if not meaning.strip():
        raise ValueError("A glossary meaning is required")
    if not literal_translation.strip():
        raise ValueError("An English translation is required")
    return GlossaryEntry(
        arabic_term=arabic_term.strip(),
        meaning=meaning.strip(),
        literal_translation=literal_translation.strip(),
        normalized_words=canonical.normalized_words,
        vocalized_words=canonical.vocalized_words,
        has_tashkeel=canonical.has_tashkeel,
        forms=(canonical, *_parse_variations(arabic_variations)),
        alternative_context_meanings=alternative_context_meanings.strip(),
        is_divine_name=is_divine_name,
    )


def merge_glossary_entries(
    custom_entries: tuple[GlossaryEntry, ...] | list[GlossaryEntry],
    base_entries: tuple[GlossaryEntry, ...] | None = None,
) -> tuple[GlossaryEntry, ...]:
    """Put mosque terms first and replace the matching built-in sense."""
    custom = tuple(custom_entries)
    base = base_entries if base_entries is not None else load_glossary()

    def overridden(entry: GlossaryEntry) -> bool:
        for replacement in custom:
            if replacement.has_tashkeel:
                if entry.has_tashkeel and entry.vocalized_words == replacement.vocalized_words:
                    return True
            elif entry.normalized_words == replacement.normalized_words:
                return True
        return False

    return (*custom, *(entry for entry in base if not overridden(entry)))


@lru_cache(maxsize=4)
def load_glossary(path: Path | None = None) -> tuple[GlossaryEntry, ...]:
    glossary_path = (path or get_settings().glossary_path).resolve()
    with glossary_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"Arabic term", "Meaning", "Literal translation"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(
                "The glossary CSV must contain Arabic term, Meaning, and "
                "Literal translation columns"
            )
        entries: list[GlossaryEntry] = []
        seen: set[tuple[tuple[str, ...], str]] = set()
        for row in [*reader, *SUPPLEMENTAL_GLOSSARY_ROWS]:
            if glossary_path == get_settings().glossary_path.resolve():
                row = row | BUILTIN_CORRECTIONS.get(_row_value(row, "Arabic term"), {})
            arabic_term = _row_value(row, "Arabic term")
            meaning = _row_value(row, "Meaning")
            literal_translation = _row_value(row, "Literal translation")
            canonical = _make_form(arabic_term, literal_translation)
            if canonical is None or not meaning:
                continue
            duplicate_key = (canonical.vocalized_words, meaning)
            if duplicate_key in seen:
                continue
            seen.add(duplicate_key)
            entries.append(build_glossary_entry(
                arabic_term=arabic_term,
                meaning=meaning,
                literal_translation=literal_translation,
                arabic_variations=_row_value(row, "Arabic variations + translation"),
                alternative_context_meanings=_row_value(row, "Alternative context meaning(s)"),
                is_divine_name=(
                    glossary_path == get_settings().glossary_path.resolve()
                    and row.get("Sense") != "ordinary"
                    and _divine_name_rendering(arabic_term) is not None
                ),
            ))
    return tuple(entries)


def _arabic_tokens(value: str) -> tuple[ArabicToken, ...]:
    normalized = _normalized_arabic(value, preserve_tashkeel=False)
    vocalized = _normalized_arabic(value, preserve_tashkeel=True)
    return tuple(
        ArabicToken(plain, marked, bool(ARABIC_MARKS_RE.search(marked)))
        for plain, marked in zip(normalized, vocalized, strict=True)
    )


def _word_alignment(value: str, candidate: str, allow_prefix: bool) -> ArabicWordAlignment | None:
    actual_forms = [(value, 0)]
    if allow_prefix:
        remainder = value
        removed = 0
        while removed < 3 and remainder and remainder[0] in COMMON_PREFIXES:
            remainder = remainder[1:]
            removed += 1
            actual_forms.append((remainder, removed))

    for actual, actual_prefix_bases in actual_forms:
        if actual == candidate:
            return ArabicWordAlignment(actual_prefix_bases, 0)
        if candidate.startswith("ال") and actual == candidate[2:]:
            return ArabicWordAlignment(actual_prefix_bases, 2)
        if actual.startswith("ال") and actual[2:] == candidate:
            return ArabicWordAlignment(actual_prefix_bases + 2, 0)
    return None


def _strip_vocalized_bases(value: str, count: int) -> str:
    letters = list(ARABIC_LETTER_WITH_MARKS_RE.finditer(value))
    return "".join(match.group(0) for match in letters[count:])


def _vocalization_compatible(actual: str, expected: str) -> bool:
    actual_letters = [
        (match.group(1), frozenset(match.group(2)))
        for match in ARABIC_LETTER_WITH_MARKS_RE.finditer(actual)
    ]
    expected_letters = [
        (match.group(1), frozenset(match.group(2)))
        for match in ARABIC_LETTER_WITH_MARKS_RE.finditer(expected)
    ]
    if len(actual_letters) != len(expected_letters):
        return False
    for (actual_base, actual_marks), (expected_base, expected_marks) in zip(
        actual_letters, expected_letters, strict=True
    ):
        if actual_base != expected_base:
            return False
        # A glossary lemma often omits the final case ending while sermon text supplies it.
        # Only enforce marks explicitly present in the glossary form; accept extra marks on an
        # otherwise unmarked letter, such as الرَّانُ matching the glossary lemma الرَّان.
        if expected_marks and actual_marks and not actual_marks.issubset(expected_marks):
            return False
    return True


def _sequence_matches(
    words: tuple[ArabicToken, ...], form: GlossaryForm
) -> list[tuple[int, bool, int]]:
    if len(form.normalized_words) > len(words):
        return []
    matches: list[tuple[int, bool, int]] = []
    for position in range(len(words) - len(form.normalized_words) + 1):
        alignments: list[ArabicWordAlignment] = []
        for index, expected in enumerate(form.normalized_words):
            alignment = _word_alignment(
                words[position + index].normalized,
                expected,
                allow_prefix=index == 0,
            )
            if alignment is None:
                break
            alignments.append(alignment)
        else:
            actual_slice = words[position : position + len(form.normalized_words)]
            has_actual_tashkeel = any(word.has_tashkeel for word in actual_slice)
            specific = False
            if has_actual_tashkeel and form.has_tashkeel:
                compatible = all(
                    _vocalization_compatible(
                        _strip_vocalized_bases(actual.vocalized, alignment.actual_prefix_bases),
                        _strip_vocalized_bases(expected, alignment.expected_prefix_bases),
                    )
                    for actual, expected, alignment in zip(
                        actual_slice,
                        form.vocalized_words,
                        alignments,
                        strict=True,
                    )
                )
                if not compatible:
                    continue
                specific = True
            alignment_cost = sum(
                alignment.actual_prefix_bases + alignment.expected_prefix_bases
                for alignment in alignments
            )
            matches.append((position, specific, alignment_cost))
    return matches


def _glossary_hits_in_arabic(
    arabic_text: str, entries: tuple[GlossaryEntry, ...] | None = None
) -> list[GlossaryHit]:
    words = _arabic_tokens(arabic_text)
    hits: list[GlossaryHit] = []
    for order, entry in enumerate(entries or load_glossary()):
        for form in entry.forms:
            for position, specific, alignment_cost in _sequence_matches(words, form):
                if entry.is_divine_name:
                    # Do not turn Ali, a scholar, or an ordinary adjective into
                    # a divine name by stripping the article or matching a root.
                    actual = words[position].normalized
                    expected = form.normalized_words[0]
                    if actual not in {expected, "و" + expected, "ف" + expected}:
                        continue
                    preceding = [word.normalized for word in words[max(0, position - 6):position]]
                    if preceding and preceding[-1] == "عبد":
                        continue
                    if not any(
                        word in {"الله", "لله", "بالله", "والله", "ربنا", "ربكم", "ربه", "ربي"}
                        for word in preceding
                    ):
                        continue
                hits.append(
                    GlossaryHit(
                        entry,
                        form,
                        position,
                        order,
                        specific,
                        alignment_cost,
                    )
                )

    specific_groups = {
        (hit.position, hit.form.normalized_words) for hit in hits if hit.specific_vocalization
    }
    hits = [
        hit
        for hit in hits
        if hit.specific_vocalization
        or (hit.position, hit.form.normalized_words) not in specific_groups
    ]
    minimum_alignment_cost = {
        (hit.position, len(hit.form.normalized_words)): min(
            candidate.alignment_cost
            for candidate in hits
            if candidate.position == hit.position
            and len(candidate.form.normalized_words) == len(hit.form.normalized_words)
        )
        for hit in hits
    }
    hits = [
        hit
        for hit in hits
        if hit.alignment_cost
        == minimum_alignment_cost[(hit.position, len(hit.form.normalized_words))]
    ]
    return sorted(
        hits,
        key=lambda hit: (hit.position, -len(hit.form.normalized_words), hit.order),
    )


def glossary_entries_in_arabic(
    arabic_text: str, entries: tuple[GlossaryEntry, ...] | None = None
) -> list[GlossaryEntry]:
    found: list[GlossaryEntry] = []
    seen: set[str] = set()
    for hit in _glossary_hits_in_arabic(arabic_text, entries):
        if hit.entry.key not in seen:
            found.append(hit.entry)
            seen.add(hit.entry.key)
    return found


def _matching_form(value: str, entry: GlossaryEntry) -> GlossaryForm | None:
    tokens = _arabic_tokens(value)
    hits = [
        (form, specific)
        for form in entry.forms
        for position, specific, _alignment_cost in _sequence_matches(tokens, form)
        if position == 0 and len(form.normalized_words) == len(tokens)
    ]
    specific = [form for form, is_specific in hits if is_specific]
    return specific[0] if specific else (hits[0][0] if hits else None)


def _english_renderings(entry: GlossaryEntry, form: GlossaryForm) -> list[str]:
    if entry.is_divine_name and (rendering := _divine_name_rendering(entry.arabic_term)):
        phrases = rendering.split("; ")
        return sorted({*phrases, *(p.removeprefix("the ") for p in phrases)}, key=len, reverse=True)
    values = [form.translation, entry.literal_translation]
    values.extend(REVIEWED_FORM_RENDERINGS.get(form.normalized_words, ()))
    if form.normalized_words == entry.normalized_words:
        values.extend(REVIEWED_ENGLISH_RENDERINGS.get(entry.arabic_term, ()))
    values.extend(candidate.translation for candidate in entry.forms)
    phrases = {
        phrase.strip() for value in values for phrase in re.split(r"[;|]", value) if phrase.strip()
    }
    phrases.update(
        match.group("phrase").strip(" ,.;:!?")
        for match in ENGLISH_QUOTED_PHRASE_RE.finditer(entry.meaning)
    )
    lead = re.split(r"[.;]", entry.meaning, maxsplit=1)[0]
    lead = lead.split(",", maxsplit=1)[0].strip()
    lead_variants = [lead]
    first_word = ENGLISH_WORD_RE.match(lead)
    if first_word and first_word.group(0).lower().endswith("ely"):
        lead_variants.append(first_word.group(0)[:-2] + lead[first_word.end() :])
    for lead_variant in lead_variants:
        lead_words = list(ENGLISH_WORD_RE.finditer(lead_variant))
        for end in range(2, len(lead_words) + 1):
            phrase = lead_variant[: lead_words[end - 1].end()].strip()
            if (
                sum(word.group(0).lower() not in ENGLISH_CONNECTORS for word in lead_words[:end])
                >= 2
            ):
                phrases.add(phrase)
    return sorted(phrases, key=len, reverse=True)


def _rendering_pattern(phrase: str, *, at_end: bool = False) -> re.Pattern[str]:
    """Match typography variants while keeping offsets in the original text.

    A single wrapped line is allowed, but never a paragraph break. Hyphens and
    apostrophes are typographic equivalents, not permission to guess synonyms.
    """
    separator = r"(?:[^\S\r\n]+|[^\S\r\n]*\r?\n[^\S\r\n]*)"
    parts = []
    for word in phrase.split():
        parts.append("".join(
            "['’]" if character in "'’" else "[-‐‑]" if character in "-‐‑"
            else re.escape(character)
            for character in word
        ))
    expression = separator.join(parts)
    ending = r"\Z" if at_end else r"(?![\w‐‑-])"
    return re.compile(r"(?<![\w‐‑-])" + expression + ending, re.IGNORECASE)


def ensure_glossary_parentheticals(
    arabic_text: str,
    translated_text: str,
    applicable_terms: list[str],
    entries: tuple[GlossaryEntry, ...] | None = None,
    protected_spans: list[tuple[int, int]] | None = None,
) -> tuple[str, list[str]]:
    """Attach selected glossary Arabic to the full matching English expression in code."""
    protected_spans = [*(protected_spans or []), *quotation_glossary_spans(translated_text)]
    matching_text = _mask_spans(translated_text, protected_spans)
    selected = [term.strip() for term in applicable_terms if _normalized_arabic(term, False)]
    insertions: list[tuple[int, str]] = []
    issues: list[str] = []
    handled_entries: set[str] = set()
    for hit in _glossary_hits_in_arabic(arabic_text, entries):
        if hit.entry.key in handled_entries:
            continue
        selected_match = next(
            (
                (term, form)
                for term in selected
                if (form := _matching_form(term, hit.entry)) is not None
            ),
            None,
        )
        if selected_match is None:
            continue
        handled_entries.add(hit.entry.key)
        if _parenthetical_display_term(matching_text, hit.entry) is not None:
            continue
        rendering_match: re.Match[str] | None = None
        selected_term, selected_form = selected_match
        for rendering in _english_renderings(hit.entry, selected_form):
            pattern = _rendering_pattern(rendering)
            rendering_match = pattern.search(matching_text)
            if rendering_match is not None:
                break
        if rendering_match is None:
            issues.append(
                f"Selected glossary term {selected_term} has no recognizable English "
                "wording to annotate; review it manually."
            )
            continue
        insertions.append((rendering_match.end(), f" ({selected_term})"))
    for key, (_display, arabic, _form, _start, end) in _unmarked_display_terms(
        arabic_text, matching_text, entries
    ).items():
        if key not in handled_entries:
            insertions.append((end, f" ({arabic})"))
    for position, insertion in sorted(set(insertions), reverse=True):
        # Never insert Arabic into authoritative wording, including its final word.
        if any(start < position <= end for start, end in protected_spans):
            continue
        translated_text = translated_text[:position] + insertion + translated_text[position:]
    return translated_text, issues


def _current_english_clause(value: str) -> str:
    boundaries = list(ENGLISH_CLAUSE_BOUNDARY_RE.finditer(value))
    start = boundaries[-1].end() if boundaries else 0
    return value[start:].lstrip()


def _preceding_english_expression(
    preceding: str, entry: GlossaryEntry, form: GlossaryForm
) -> str | None:
    preceding = preceding.rstrip()
    divine_rendering = _divine_name_rendering(entry.arabic_term)
    if not entry.is_divine_name and divine_rendering:
        if any(_rendering_pattern(p.removeprefix("the "), at_end=True).search(preceding)
               for p in divine_rendering.split("; ")):
            return None
    for phrase in _english_renderings(entry, form):
        if match := _rendering_pattern(phrase, at_end=True).search(preceding):
            return match.group()
    # Arabic word count cannot determine the length of an English expression.
    # If wording is unknown, expose the Arabic note instead of highlighting an
    # arbitrary final English word (or borrowing words from the previous line).
    return None


def _parenthetical_display_term(
    translated_text: str, entry: GlossaryEntry
) -> tuple[str, str, GlossaryForm, int, int] | None:
    for match in PARENTHETICAL_RE.finditer(translated_text):
        arabic = match.group("arabic").strip()
        form = _matching_form(arabic, entry)
        if form is None:
            continue
        display = _preceding_english_expression(translated_text[: match.start()], entry, form)
        if display:
            preceding = translated_text[: match.start()].rstrip()
            end = len(preceding)
            return display, arabic, form, end - len(display), end
    return None


def popup_phrase_from_text(preceding: str, entry: GlossaryEntry, form: GlossaryForm) -> str:
    """A popup heading must be copied from this occurrence, not translated again."""
    preceding = preceding.rstrip()
    aliases = {
        phrase
        for arabic in (entry.arabic_term, form.arabic_term)
        for phrase in POPUP_RENDERINGS.get(ARABIC_MARKS_RE.sub("", arabic), ())
    }
    phrases = sorted(set(_english_renderings(entry, form)) | set(aliases), key=len, reverse=True)
    for phrase in phrases:
        if match := _rendering_pattern(phrase, at_end=True).search(preceding):
            return match.group()
    # We cannot reliably infer an arbitrary expression's length from the Arabic.
    # Show the actual local clause rather than a dictionary synonym or its last word.
    return popup_context_from_text(preceding)


def popup_context_from_text(preceding: str) -> str:
    context = re.split(r"[\r\n.!?;:…,)]+", preceding.rstrip())[-1].strip(" \t‘’\"“”")
    return context if ENGLISH_WORD_RE.search(context) else ""


def _arabic_display_term(
    translated_text: str, entry: GlossaryEntry
) -> tuple[str, str, GlossaryForm, int, int] | None:
    if entry.is_divine_name:
        return None
    for match in ARABIC_RUN_RE.finditer(translated_text):
        arabic = match.group(0)
        form = _matching_form(arabic, entry)
        if form is not None:
            return arabic, arabic, form, match.start(), match.end()
    return None


def _unmarked_display_terms(
    arabic_text: str,
    translated_text: str,
    entries: tuple[GlossaryEntry, ...] | None,
) -> dict[str, tuple[str, str, GlossaryForm, int, int]]:
    """Fallback only to explicit CSV renderings of a form present in the Arabic.

    Never infer an English phrase from the explanation, nor borrow a different verb
    form's rendering. Conflicting glossary senses for the same span are left unmarked.
    """
    candidates: dict[tuple[int, int], dict[str, tuple[str, str, GlossaryForm, int, int]]] = {}
    hits = _glossary_hits_in_arabic(arabic_text, entries)
    marked = {
        hit.entry.key: display
        for hit in hits
        if (display := _parenthetical_display_term(translated_text, hit.entry)) is not None
    }
    for hit in hits:
        if hit.entry.key in marked:
            continue
        renderings = re.split(r"[;|]", hit.form.translation or hit.entry.literal_translation)
        renderings.extend(REVIEWED_FORM_RENDERINGS.get(hit.form.normalized_words, ()))
        if hit.form.normalized_words == hit.entry.normalized_words:
            renderings.extend(REVIEWED_ENGLISH_RENDERINGS.get(hit.entry.arabic_term, ()))
        for rendering in renderings:
            rendering = rendering.strip()
            if not rendering:
                continue
            pattern = _rendering_pattern(rendering)
            for match in pattern.finditer(translated_text):
                if any(
                    match.start() < item[4] and item[3] < match.end()
                    for item in marked.values()
                ):
                    continue
                candidates.setdefault(match.span(), {})[hit.entry.key] = (
                    match.group(), hit.form.arabic_term, hit.form, *match.span()
                )
    result = {}
    used_spans: list[tuple[int, int]] = []
    # Prefer complete phrases over another entry matching only their last word.
    for (start, end), meanings in sorted(
        candidates.items(), key=lambda item: (-(item[0][1] - item[0][0]), item[0][0])
    ):
        if len(meanings) != 1 or any(start < right and left < end for left, right in used_spans):
            continue
        key, value = next(iter(meanings.items()))
        used_spans.append((start, end))
        if key not in result or start < result[key][3]:
            result[key] = value
    return result


def glossary_matches(
    arabic_text: str,
    translated_text: str,
    seen_terms: set[object] | None = None,
    entries: tuple[GlossaryEntry, ...] | None = None,
    protected_spans: list[tuple[int, int]] | None = None,
    arabic_only: bool = False,
    popup_phrases: list[dict] | None = None,
) -> list[GlossaryMatch]:
    from app.services.glossary_phrases import phrase_at_note

    original_text = translated_text
    translated_text = _mask_spans(translated_text, protected_spans or [])
    seen = seen_terms if seen_terms is not None else set()
    matches: list[GlossaryMatch] = []
    fallback = _unmarked_display_terms(arabic_text, translated_text, entries)
    for hit in _glossary_hits_in_arabic(arabic_text, entries):
        entry = hit.entry
        if entry.key in seen or entry.normalized_words in seen:
            continue
        display = _parenthetical_display_term(translated_text, entry)
        english_phrase = display[0] if display else ""
        if (not entry.is_divine_name
                and _divine_name_rendering(entry.arabic_term) and display is None):
            continue
        if arabic_only:
            if entry.is_divine_name and display is None:
                continue
            arabic_display = None
            for note in PARENTHETICAL_RE.finditer(translated_text):
                arabic = note.group("arabic").strip()
                form = _matching_form(arabic, entry)
                if form is None:
                    continue
                english_phrase = popup_phrase_from_text(translated_text[:note.start()], entry, form)
                occurrence = sum(
                    previous.group('arabic').strip() == arabic
                    for previous in PARENTHETICAL_RE.finditer(original_text[:note.start()])
                )
                for annotation in popup_phrases or []:
                    if (annotation.get('arabic_term') == arabic
                            and annotation.get('arabic_occurrence', 0) == occurrence):
                        exact = phrase_at_note(original_text[:note.start()],
                                              annotation.get('phrase', ''))
                        if exact:
                            english_phrase = exact
                            break
                if _divine_name_rendering(entry.arabic_term):
                    phrase = _preceding_english_expression(
                        translated_text[:note.start()], entry, form)
                    if phrase is None:
                        continue
                    english_phrase = phrase
                start = note.start("arabic") + len(note.group("arabic")) - len(
                    note.group("arabic").lstrip()
                )
                arabic_display = (arabic, arabic, form, start, start + len(arabic))
                break
            if arabic_display is None:
                continue
            display = arabic_display
        if display is None:
            display = _arabic_display_term(translated_text, entry)
        if display is None:
            display = fallback.get(entry.key)
        if display is None:
            continue
        display_term, arabic_term, displayed_form, translation_start, translation_end = display
        seen.add(entry.key)
        matches.append(
            GlossaryMatch(
                entry=entry,
                display_term=display_term,
                arabic_term=arabic_term,
                literal_translation=(displayed_form.translation or entry.literal_translation),
                translation_start=translation_start,
                translation_end=translation_end,
                english_phrase=english_phrase,
            )
        )
    return matches


def _mask_spans(text: str, spans: list[tuple[int, int]]) -> str:
    characters = list(text)
    for start, end in spans:
        if 0 <= start < end <= len(text):
            characters[start:end] = "\n" * (end - start)
    return "".join(characters)


def quotation_glossary_spans(
    text: str, citations: list[dict[str, object]] | None = None,
) -> list[tuple[int, int]]:
    """Keep quotation wording free of automatic glossary annotations.

    Also protect bounded quotations without citations, e.g. a hadith still awaiting
    source verification. No hard-word exceptions are enabled without a reviewed list.
    """
    # This is display filtering, not PDF segmentation. A damaged English quote
    # must not hide every glossary note in the rest of a sermon segment.
    # Preserve complete multiline quotes; bound unmatched ones by paragraphs.
    pairs = dict(zip("«“‘❝‹「『《〈﴿", "»”’❞›」』》〉﴾", strict=True))
    stack: list[tuple[str, int]] = []
    spans: list[tuple[int, int]] = []
    for index, character in enumerate(text):
        if character == "\n" and re.match(r"\n[ \t]*\n", text[index:]):
            spans.extend((start, index) for _, start in stack)
            stack.clear()
            continue
        if character in {"'", "’"} and 0 < index < len(text) - 1:
            if text[index - 1].isalnum() and text[index + 1].isalnum():
                continue
        # A matching outer closer recovers from mismatched nested typography.
        matching = next((i for i in range(len(stack)-1, -1, -1)
                         if stack[i][0] == character), None)
        if matching is not None:
            _, start = stack[matching]
            spans.append((start, index + 1))
            del stack[matching:]
        elif character in pairs:
            stack.append((pairs[character], index))
        elif character in {'"', "'"}:
            stack.append((character, index))
    spans.extend((start, len(text)) for _, start in stack)
    for citation in citations or []:
        if citation.get("source_kind") not in {"quran", "hadith"}:
            continue
        start, end = citation.get("translation_start"), citation.get("translation_end")
        excerpt = str(citation.get("excerpt") or "")
        if (isinstance(start, int) and isinstance(end, int)
                and 0 <= start < end <= len(text) and text[start:end] == excerpt):
            spans.append((start, end))
        elif excerpt:
            spans.extend(match.span() for match in re.finditer(re.escape(excerpt), text))
    return spans
