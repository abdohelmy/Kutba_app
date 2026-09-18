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
        "ى": "ي",
        "ؤ": "و",
        "ئ": "ي",
        "ـ": "",
    }
)
COMMON_PREFIXES = ("و", "ف", "ب", "ك", "ل")
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
    return " ".join(_normalized_arabic(value, preserve_tashkeel=False))


def build_glossary_entry(
    arabic_term: str,
    meaning: str,
    literal_translation: str,
    arabic_variations: str = "",
    alternative_context_meanings: str = "",
) -> GlossaryEntry:
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
    values = [form.translation, entry.literal_translation]
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


def ensure_glossary_parentheticals(
    arabic_text: str,
    translated_text: str,
    applicable_terms: list[str],
    entries: tuple[GlossaryEntry, ...] | None = None,
) -> tuple[str, list[str]]:
    """Attach selected glossary Arabic to the full matching English expression in code."""
    selected = [term.strip() for term in applicable_terms if _normalized_arabic(term, False)]
    if not selected:
        return translated_text, []
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
        if _parenthetical_display_term(translated_text, hit.entry) is not None:
            continue
        rendering_match: re.Match[str] | None = None
        selected_term, selected_form = selected_match
        for rendering in _english_renderings(hit.entry, selected_form):
            pattern = re.compile(
                rf"(?<![A-Za-z0-9]){re.escape(rendering)}(?![A-Za-z0-9])",
                re.IGNORECASE,
            )
            rendering_match = pattern.search(translated_text)
            if rendering_match is not None:
                break
        if rendering_match is None:
            issues.append(
                f"Selected glossary term {selected_term} has no recognizable English "
                "wording to annotate; review it manually."
            )
            continue
        insertions.append((rendering_match.end(), f" ({selected_term})"))
    for position, insertion in sorted(insertions, reverse=True):
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
    for phrase in _english_renderings(entry, form):
        if not preceding.lower().endswith(phrase.lower()):
            continue
        start = len(preceding) - len(phrase)
        if start == 0 or not preceding[start - 1].isalnum():
            return preceding[start:]

    clause = _current_english_clause(preceding)
    words = list(ENGLISH_WORD_RE.finditer(clause))
    if not words:
        return None
    required_content_words = max(1, len(form.normalized_words))
    content_words = 0
    start_index = len(words) - 1
    for index in range(len(words) - 1, -1, -1):
        start_index = index
        if words[index].group(0).lower() not in ENGLISH_CONNECTORS:
            content_words += 1
        if content_words >= required_content_words:
            break
    return clause[words[start_index].start() : words[-1].end()]


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


def _arabic_display_term(
    translated_text: str, entry: GlossaryEntry
) -> tuple[str, str, GlossaryForm, int, int] | None:
    for match in ARABIC_RUN_RE.finditer(translated_text):
        arabic = match.group(0)
        form = _matching_form(arabic, entry)
        if form is not None:
            return arabic, arabic, form, match.start(), match.end()
    return None


def glossary_matches(
    arabic_text: str,
    translated_text: str,
    seen_terms: set[object] | None = None,
    entries: tuple[GlossaryEntry, ...] | None = None,
) -> list[GlossaryMatch]:
    seen = seen_terms if seen_terms is not None else set()
    matches: list[GlossaryMatch] = []
    for hit in _glossary_hits_in_arabic(arabic_text, entries):
        entry = hit.entry
        if entry.key in seen or entry.normalized_words in seen:
            continue
        display = _parenthetical_display_term(translated_text, entry)
        if display is None:
            display = _arabic_display_term(translated_text, entry)
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
            )
        )
    return matches
