import pytest

from app.services.glossary import glossary_matches, quotation_glossary_spans
from app.services.glossary_transliteration import transliterate_letters


def test_arabic_link_preserves_whole_expression_and_english_title():
    text = "🌙 I counsel you and myself (أوصيكم ونفسي)."
    term = glossary_matches("أوصيكم ونفسي", text, arabic_only=True)[0]
    assert term.display_term == "أوصيكم ونفسي"
    assert text[term.translation_start:term.translation_end] == "أوصيكم ونفسي"
    assert term.english_phrase == "I counsel you and myself"


def test_unrecognized_english_still_gets_arabic_link():
    text = "Cultivate mindful devotion (التقوى)."
    term = glossary_matches("التقوى", text, arabic_only=True)[0]
    assert term.display_term == "التقوى"
    assert term.english_phrase == "Cultivate mindful devotion"


@pytest.mark.parametrize("arabic,phrase", [
    ("النفس", "self"), ("القضاء", "divine decree"),
    ("القدر", "measured apportionment"), ("السراء", "prosperity"),
    ("الضراء", "adversity"), ("الأَجَل", "appointed terms"),
    ("السَّبَب", "means of safety"), ("الجَنَّة", "Paradise"),
    ("النَّار", "Hell"), ("النَّعِيم", "bliss"),
    ("الذِّكْر", "remembrance of Allah"), ("كُفْرَان", "ingratitude for blessings"),
    ("الفتنة", "trials"), ("دار السلام", "Abode of Peace"),
    ("جَزاء", "recompense"), ("إلهَ", "deity"),
    ("الزُّهدُ", "most detached"), ("الإمامُ", "Imam"),
    ("المَعْروف", "recognized good"),
])
def test_popup_uses_actual_sermon_wording(arabic, phrase):
    text = f"We speak about {phrase} ({arabic})."
    term = glossary_matches(arabic, text, arabic_only=True)[0]
    assert term.english_phrase == phrase


def test_unknown_heading_never_borrows_previous_line_or_dictionary_translation():
    text = "Earlier wording.\nA fresh contextual expression (التقوى)."
    term = glossary_matches("التقوى", text, arabic_only=True)[0]
    assert term.english_phrase == "A fresh contextual expression"


def test_explicit_phrase_preserves_full_expression_and_rejects_stale_metadata():
    text = 'He was the most detached (الزهد).'
    annotations = [dict(arabic_term='الزهد', arabic_occurrence=0, phrase='the most detached')]
    assert glossary_matches('الزهد', text, arabic_only=True,
                            popup_phrases=annotations)[0].english_phrase == 'the most detached'
    annotations[0]['phrase'] = 'asceticism'
    assert glossary_matches('الزهد', text, arabic_only=True,
                            popup_phrases=annotations)[0].english_phrase == 'most detached'


def test_no_english_fallback_or_links_inside_quotes():
    assert not glossary_matches("التقوى", "Cultivate God-consciousness.", arabic_only=True)
    text = '“Cultivate God-consciousness (التقوى).”'
    assert not glossary_matches("التقوى", text, arabic_only=True,
                               protected_spans=quotation_glossary_spans(text))


def test_transliteration_uses_explicit_vowels_and_shadda():
    assert transliterate_letters("عِلْم") == "ʿilm"
    assert transliterate_letters("حَقّ") == "ḥaqq"
    assert transliterate_letters("علم") == "ʿlm"  # Do not guess missing vowels.
