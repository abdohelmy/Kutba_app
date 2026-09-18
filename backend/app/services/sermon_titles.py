import re
from datetime import date

ARABIC_RE = re.compile(r"[\u0600-\u06FF]")
LATIN_RE = re.compile(r"[A-Za-z]")
SPACE_RE = re.compile(r"\s+")
SOURCE_HEADING_RE = re.compile(
    r"^(?:عنوان\s+)?(?:خطبة\s+(?:الجمعة|جمعه)|الخطبة|الخطبه)\s*[:：\-–—]?\s*",
    re.IGNORECASE,
)
TRANSLATED_HEADING_RE = re.compile(
    r"^(?:title|friday\s+(?:khutba|sermon)|khutba|sermon)\s*[:：\-–—]\s*",
    re.IGNORECASE,
)
SOURCE_BOILERPLATE = (
    "بسم الله",
    "الحمد لله",
    "إن الحمد لله",
    "ان الحمد لله",
    "أشهد أن",
    "اشهد ان",
    "أما بعد",
    "اما بعد",
    "أوصيكم",
    "اوصيكم",
    "قال الله",
    "قال تعالى",
    "قال تعالي",
    "قال رسول الله",
    "الصلاة والسلام",
    "اللهم صل",
)
TRANSLATED_BOILERPLATE = (
    "all praise",
    "praise be",
    "in the name of allah",
    "i bear witness",
    "to proceed",
    "as for what follows",
    "i counsel you",
    "i advise you",
    "o servants of allah",
    "dear brothers",
    "may allah's peace",
    "peace and blessings",
)


def _lines(value: str) -> list[str]:
    return [
        SPACE_RE.sub(" ", line).strip(" \t\r\n#*•_|")
        for line in value.splitlines()
        if line.strip(" \t\r\n#*•_|")
    ]


def _reasonable_title(value: str, *, max_words: int = 16) -> bool:
    return 2 <= len(value.split()) <= max_words and 4 <= len(value) <= 180


def default_sermon_title(khutba_date: date) -> str:
    return f"Friday Khutba — {khutba_date.strftime('%d %B %Y')}"


def infer_source_title(arabic_text: str, khutba_date: date) -> str:
    """Choose an explicit or compact Arabic heading, with a stable dated fallback."""
    lines = _lines(arabic_text)
    for line in lines[:20]:
        stripped = SOURCE_HEADING_RE.sub("", line).strip(" :：-–—")
        if stripped != line and _reasonable_title(stripped):
            return stripped[:250]
    for line in lines[:20]:
        normalized = line.casefold()
        if any(normalized.startswith(prefix.casefold()) for prefix in SOURCE_BOILERPLATE):
            continue
        if ARABIC_RE.search(line) and _reasonable_title(line, max_words=12):
            return line[:250]
    return default_sermon_title(khutba_date)


def infer_translated_title(
    translated_segments: list[str],
    current_title: str,
    khutba_date: date,
) -> str:
    """Prefer an English heading already produced as part of the translated sermon."""
    lines = [line for text in translated_segments[:3] for line in _lines(text)]
    for line in lines[:30]:
        candidate = TRANSLATED_HEADING_RE.sub("", line).strip(" :：-–—")
        if candidate != line and _is_translated_title(candidate):
            return candidate[:250]
    for line in lines[:30]:
        if _is_translated_title(line) and not line.endswith((".", "!", "?", ";")):
            return line[:250]
    return current_title or default_sermon_title(khutba_date)


def _is_translated_title(value: str) -> bool:
    normalized = value.casefold()
    if any(normalized.startswith(prefix) for prefix in TRANSLATED_BOILERPLATE):
        return False
    if not _reasonable_title(value, max_words=14):
        return False
    return len(LATIN_RE.findall(value)) >= 4 and len(LATIN_RE.findall(value)) > len(
        ARABIC_RE.findall(value)
    )
