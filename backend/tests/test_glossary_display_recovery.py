import pytest

from app.services.glossary import glossary_matches, quotation_glossary_spans


def links(arabic, text, citations=None):
    return glossary_matches(arabic, text, arabic_only=True,
                            protected_spans=quotation_glossary_spans(text, citations))


def test_mismatched_nested_quote_does_not_hide_following_prose():
    text = 'He said: “I fear they will kill me."” Then divine decree (القضاء).'
    assert any(m.arabic_term == "القضاء" for m in links("القضاء", text))


def test_unclosed_quote_stops_at_paragraph_boundary():
    text = '“A quotation with "mixed punctuation.\n\nIngratitude (كفران) is harmful.'
    assert any(m.entry.arabic_term == "الكفران" for m in links("كفران", text))


def test_actual_quotes_and_canonical_spans_remain_protected():
    text = '“Remember\nGod-consciousness (التقوى).”'
    assert not links("التقوى", text)
    text = 'God-consciousness (التقوى) protects you.\n\nKeep faith.'
    assert not links("التقوى", text, [{"source_kind": "hadith", "excerpt": text,
                                      "translation_start": 0, "translation_end": len(text)}])


@pytest.mark.parametrize(("arabic", "english"), [("السلام", "peace"), ("المؤمن", "believer")])
def test_ordinary_senses_are_not_removed_by_divine_name_guard(arabic, english):
    matches = links(arabic, f"The {english} ({arabic}).")
    assert len(matches) == 1
    assert not matches[0].entry.is_divine_name


@pytest.mark.parametrize(("arabic", "english"), [
    ("السلام", "Source of Peace"), ("المؤمن", "Giver of Security"), ("العلي", "Most High")])
def test_divine_senses_are_not_replaced_by_ordinary_senses(arabic, english):
    matches = links(f"الله {arabic}", f"Allah, the {english} ({arabic}).")
    assert len(matches) == 1
    assert matches[0].entry.is_divine_name


def test_most_high_without_the_is_recognized_but_inflation_is_not():
    assert links("الله العلي", "Allah Most High (العلي).")
    assert not links("العلي", "High (العلي) inflation.")


def test_same_arabic_spelling_links_each_sense_at_its_own_occurrence():
    text = "Allah is the Source of Peace (السلام). We seek peace (السلام)."
    matches = links("الله السلام ونسأل السلام", text)
    assert len(matches) == 2
    divine = next(m for m in matches if m.entry.is_divine_name)
    ordinary = next(m for m in matches if not m.entry.is_divine_name)
    assert divine.translation_start == text.index("السلام")
    assert ordinary.translation_start == text.rindex("السلام")


@pytest.mark.parametrize(("arabic", "english"), [
    ("الآجال", "appointed terms"),
    ("سَنَدٍ حَسَنٍ", "hasan chain of transmission"),
    ("سَنَدٍ صَحِيحٍ", "authentic chain of transmission"),
    ("الحديث القدسي", "sacred hadith"),
    ("مَعِيَّةُ اللهِ", "Allah's accompanying presence"),
    ("أَهْلُ الذِّكْرِ", "people of the Reminder and knowledge"),
])
def test_complete_expressions_get_definitions(arabic, english):
    matches = links(arabic, f"Consider {english} ({arabic}).")
    assert len(matches) == 1
    assert matches[0].display_term == arabic
    assert matches[0].entry.meaning
