"""Deterministic letter transliteration; never invent missing Arabic vowels."""

import re

LETTERS = dict(zip(
    "ءآأإؤئابتثجحخدذرزسشصضطظعغفقكلمنهويىةٱ",
    ["ʾ", "ā", "ʾa", "ʾi", "ʾ", "ʾ", "ā", "b", "t", "th", "j", "ḥ", "kh",
     "d", "dh", "r", "z", "s", "sh", "ṣ", "ḍ", "ṭ", "ẓ", "ʿ", "gh", "f", "q",
     "k", "l", "m", "n", "h", "w", "y", "ā", "h", "a"], strict=True))
MARKS = {"َ": "a", "ِ": "i", "ُ": "u", "ً": "an", "ٍ": "in", "ٌ": "un",
         "ْ": "", "ٰ": "ā", "ـ": ""}


def transliterate_letters(arabic: str) -> str:
    words = []
    for word in arabic.split():
        word = re.sub(r"^[اٱ][َُِْ]?ل[ْ]?", "al-", word)
        result = []
        for cluster in re.finditer(r"([^\u064b-\u065f\u0670])([\u064b-\u065f\u0670]*)", word):
            character, marks = cluster.groups()
            if character in LETTERS:
                letter = LETTERS[character]
                result.append(letter * (2 if "ّ" in marks else 1))
                result.extend(MARKS.get(mark, "") for mark in marks)
            elif ord(character) < 128:
                result.append(character)
        value = "".join(result)
        # Long-vowel letters after their explicit short vowels.
        value = value.replace("aā", "ā").replace("uw", "ū").replace("iy", "ī")
        words.append(value)
    return " ".join(words)
