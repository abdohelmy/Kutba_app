from app.services.glossary import (
    ensure_glossary_parentheticals,
    glossary_entries_in_arabic,
    glossary_matches,
    load_glossary,
)


def test_backend_attaches_glossary_parenthetical_to_the_complete_expression():
    translated, issues = ensure_glossary_parentheticals(
        "أما بعد أوصيكم ونفسي",
        "To proceed: I counsel you and myself.",
        ["أوصيكم ونفسي"],
    )

    assert translated == "To proceed: I counsel you and myself (أوصيكم ونفسي)."
    assert issues == []
    match = next(
        item
        for item in glossary_matches("أوصيكم ونفسي", translated)
        if item.entry.arabic_term == "أوصيكم ونفسي"
    )
    assert translated[match.translation_start : match.translation_end] == (
        "I counsel you and myself"
    )


def test_verified_glossary_loads_variations_and_alternative_contexts():
    entries = load_glossary()

    assert len(entries) == 651
    taqwa = next(entry for entry in entries if entry.arabic_term == "التقوى")
    assert any(
        form.arabic_term == "اِتَّقَى" and "guard against" in form.translation for form in taqwa.forms
    )
    debt = next(entry for entry in entries if entry.arabic_term == "الدين")
    assert "الدَّيْن" in debt.alternative_context_meanings


def test_diacritized_variation_matches_with_an_attached_conjunction():
    entries = glossary_entries_in_arabic("وَاتَّقَى المؤمنُ ربَّه")

    assert any(entry.arabic_term == "التقوى" for entry in entries)


def test_definite_article_entry_matches_prefixed_indefinite_source_form():
    matches = glossary_matches(
        "أوصيكم ونفسي بِتَقْوَى الله",
        "I counsel you and myself to have God-consciousness (التَّقْوَى) of Allah.",
    )

    match = next(item for item in matches if item.entry.arabic_term == "التقوى")
    assert match.display_term == "God-consciousness"
    assert match.arabic_term == "التَّقْوَى"


def test_stacked_prefixes_do_not_hide_a_glossary_term():
    entries = glossary_entries_in_arabic("وبالتقوى تستقيم القلوب")

    assert any(entry.arabic_term == "التقوى" for entry in entries)


def test_tashkeel_selects_the_correct_context_for_same_unvocalized_spelling():
    entries = glossary_entries_in_arabic("تمت الخِطبة قبل عقد النكاح")

    khutbah_entries = [entry for entry in entries if entry.normalized_words == ("الخطبة",)]
    assert [entry.arabic_term for entry in khutbah_entries] == ["الخِطبة"]
    assert "marriage proposal" in khutbah_entries[0].meaning


def test_multiword_glossary_expression_is_highlighted_as_a_complete_phrase():
    matches = glossary_matches(
        "وشعر بضيق الصدر عند ذلك",
        "He experienced tightness of chest (ضيق الصدر) at that moment.",
    )

    match = next(item for item in matches if item.entry.arabic_term == "ضيق الصدر")
    assert match.display_term == "tightness of chest"
    assert match.arabic_term == "ضيق الصدر"


def test_multiword_variation_translation_is_not_reduced_to_its_final_word():
    matches = glossary_matches(
        "وَاتَّقَى المؤمنُ المعصية",
        "The believer guarded against (اِتَّقَى) sin.",
    )

    match = next(item for item in matches if item.entry.arabic_term == "التقوى")
    assert match.display_term == "guarded against"
    assert match.arabic_term == "اِتَّقَى"
    assert "guard against" in match.literal_translation


def test_definition_wording_preserves_complete_english_expression():
    matches = glossary_matches(
        "والإعراض سبب للشقاء ثم القلب الذاكر",
        (
            "Deliberate turning away (الإعراض) causes misery, while the heart of one who "
            "actively remembers and mentions Allah (الذاكر) remains alive."
        ),
    )

    assert {match.entry.arabic_term: match.display_term for match in matches} == {
        "الإعراض": "Deliberate turning away",
        "الذاكر": "one who actively remembers and mentions Allah",
    }


def test_fallback_expression_never_crosses_a_line_or_sentence_boundary():
    matches = glossary_matches(
        "أما بعد",
        "The previous sentence ends here.\n\nTo proceed (أما بعد): remember Allah.",
    )

    match = next(item for item in matches if item.entry.arabic_term == "أما بعد")
    assert match.display_term == "To proceed"


def test_requested_supplements_match_vocalized_and_ocr_forms():
    matches = glossary_matches(
        "وهو الرَّان والضَّنْك وهذه سنه الله",
        (
            "It is the stain (الرَّان), severe constriction (الضَّنْك), and Allah's "
            "established way (سنه الله)."
        ),
    )

    assert {match.entry.arabic_term: match.display_term for match in matches} == {
        "الرَّان": "stain",
        "الضنك": "severe constriction",
        "سنة الله": "Allah's established way",
    }


def test_formula_phrase_is_highlighted_in_full():
    matches = glossary_matches(
        "أما بعد أوصيكم ونفسي",
        "To proceed (أما بعد): I counsel you and myself (أوصيكم ونفسي).",
    )

    assert {match.entry.arabic_term: match.display_term for match in matches} == {
        "أما بعد": "To proceed",
        "أوصيكم ونفسي": "I counsel you and myself",
    }


def test_knowledge_is_not_treated_as_modern_science():
    knowledge = next(entry for entry in load_glossary() if entry.arabic_term == "العلم")
    assert knowledge.literal_translation == "knowledge; sacred knowledge"

    translated, issues = ensure_glossary_parentheticals(
        "العلم النافع يرفع صاحبه",
        "Sacred knowledge raises the person who possesses it.",
        ["العلم"],
    )
    assert issues == []
    assert translated.startswith("Sacred knowledge (العلم)")

    matches = glossary_matches("العلم النافع يرفع صاحبه", translated)

    match = next(item for item in matches if item.entry.arabic_term == "العلم")
    assert match.display_term == "Sacred knowledge"
    assert match.translation_start == 0
    assert match.translation_end == len("Sacred knowledge")
