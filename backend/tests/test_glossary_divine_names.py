import pytest

from app.services.glossary import (
    build_glossary_entry,
    glossary_entries_in_arabic,
    glossary_matches,
    quotation_glossary_spans,
)


def test_mosque_can_define_ordinary_sense_without_divine_remapping():
    entry = build_glossary_entry("المؤمن", "A person who believes in Allah.", "believer")
    assert not entry.is_divine_name
    matches = glossary_matches("المؤمن", "The believer (المؤمن).", entries=(entry,))
    assert len(matches) == 1
    assert matches[0].entry.meaning == "A person who believes in Allah."


def test_most_high_has_definition_and_full_expression():
    text = "We praise Allah, the Most High (العلي)."
    matches = glossary_matches("نحمد الله العَلِيّ", text)
    term = next(m for m in matches if m.entry.arabic_term == "العلي")
    assert term.display_term == "the Most High"
    assert term.entry.meaning
    assert text[term.translation_start:term.translation_end] == "the Most High"


@pytest.mark.parametrize("arabic", ["قال علي", "علا البناء", "الله يحب العالم", "حضر عبد العلي"])
def test_names_do_not_match_people_or_related_verbs(arabic):
    names = {e.arabic_term for e in glossary_entries_in_arabic(arabic)}
    assert not names.intersection({"العلي", "العليم"})


@pytest.mark.parametrize("english", ["high", "rise", "elevated"])
def test_generic_words_do_not_receive_divine_definition(english):
    matches = glossary_matches("الله العلي", f"A {english} (العلي) place.")
    assert not any(m.entry.arabic_term == "العلي" for m in matches)


def test_correct_rendering_works_without_model_parentheses():
    matches = glossary_matches("الله العليم", "Allah is the All-Knowing.")
    assert any(m.entry.arabic_term == "العليم" and m.display_term == "the All-Knowing"
               for m in matches)


def test_divine_names_do_not_override_quote_policy():
    text = '“Allah is the Most High.”'
    matches = glossary_matches("الله العلي", text,
                              protected_spans=quotation_glossary_spans(text))
    assert not matches
