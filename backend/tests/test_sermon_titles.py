from datetime import date

from app.services.sermon_titles import infer_source_title, infer_translated_title


def test_explicit_arabic_heading_is_used_as_inferred_title():
    title = infer_source_title(
        "خطبة الجمعة: الصبر والشكر\n\nالحمد لله رب العالمين ونستعينه ونستغفره.",
        date(2026, 8, 14),
    )

    assert title == "الصبر والشكر"


def test_translated_heading_replaces_an_inferred_arabic_title():
    title = infer_translated_title(
        [
            "Friday Khutba: Patience and Gratitude\n\n"
            "All praise is due to Allah, Lord of all worlds."
        ],
        "الصبر والشكر",
        date(2026, 8, 14),
    )

    assert title == "Patience and Gratitude"


def test_translation_boilerplate_does_not_become_the_title():
    title = infer_translated_title(
        ["All praise is due to Allah, Lord of all worlds."],
        "الصبر والشكر",
        date(2026, 8, 14),
    )

    assert title == "الصبر والشكر"
