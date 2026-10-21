from app.services.glossary import (
    build_glossary_entry,
    ensure_glossary_parentheticals,
    glossary_entries_in_arabic,
    glossary_matches,
    normalized_arabic_key,
    quotation_glossary_spans,
)


def test_huda_and_hady_are_not_interchangeable():
    entries = glossary_entries_in_arabic("الهُدى من الله")
    assert any(e.arabic_term == "الهدى" for e in entries)
    assert not any(e.arabic_term == "الهدي" for e in entries)
    entries = glossary_entries_in_arabic("الهَدْي في الحج")
    assert any(e.arabic_term == "الهدي" for e in entries)
    assert not any(e.arabic_term == "الهدى" for e in entries)
    assert normalized_arabic_key("الهدى") == "الهدي"  # Existing database keys remain stable.


def test_guidance_does_not_get_the_sacrificial_offering_gloss():
    matches = glossary_matches("الهُدى من الله", "Guidance (الهدى) comes from Allah.")
    term = next(m for m in matches if m.display_term == "Guidance")
    assert term.entry.arabic_term == "الهدى"
    assert "animal offering" not in term.entry.meaning
    assert not glossary_matches("الهدي في الحج", "Guidance is important.")


def test_first_ordinary_occurrence_is_highlighted_after_skipping_quote():
    text = '“God-consciousness protects you.” Then cultivate God-consciousness (التقوى).'
    seen = set()
    matches = glossary_matches("التقوى", text, seen,
        protected_spans=quotation_glossary_spans(text))
    assert len(matches) == 1
    assert matches[0].translation_start == text.rindex("God-consciousness")


def test_skipping_quoted_term_does_not_consume_first_occurrence():
    seen = set()
    text = '“God-consciousness protects you.”'
    assert not glossary_matches("التقوى", text, seen,
        protected_spans=quotation_glossary_spans(text))
    assert not seen
    assert glossary_matches("التقوى", "God-consciousness protects you.", seen)


def test_unquoted_canonical_span_is_also_protected():
    text = "God-consciousness protects you."
    citation = {"source_kind": "hadith", "excerpt": text,
                "translation_start": 0, "translation_end": len(text)}
    assert not glossary_matches("التقوى", text,
        protected_spans=quotation_glossary_spans(text, [citation]))


def test_parenthetical_is_not_inserted_at_end_of_canonical_span():
    entry = build_glossary_entry("التقوى", "Mindfulness of Allah.", "God-consciousness")
    text = "Cultivate God-consciousness"
    repaired, _ = ensure_glossary_parentheticals("التقوى", text, [], (entry,),
                                                protected_spans=[(0, len(text))])
    assert repaired == text


def test_no_automatic_arabic_added_inside_unverified_quote():
    text = 'He said: “Cultivate God-consciousness.”'
    repaired, _ = ensure_glossary_parentheticals("التقوى", text, [])
    assert repaired == text


def test_reader_preview_suppresses_quoted_glossary_but_keeps_citation(client, seeded_accounts):
    from conftest import login_headers
    from test_workflow import _seed_sermon

    from app.db.session import SessionLocal
    from app.models import Sermon, SermonStatus

    sermon_id = _seed_sermon(seeded_accounts)
    text = '“God-consciousness protects you.”'
    with SessionLocal() as db:
        sermon = db.get(Sermon, sermon_id)
        sermon.status = SermonStatus.REVIEW_REQUIRED
        segment = sermon.segments[0]
        segment.arabic_text = "التقوى"
        segment.translated_text = text
        segment.citations = [{"chunk_id": "test", "source_id": "test",
            "title": "Source", "authority": "Test", "source_kind": "hadith",
            "excerpt": text[1:-1], "translation_start": 1, "translation_end": len(text)-1}]
        db.commit()
    response = client.get(f"/api/v1/admin/sermons/{sermon_id}/preview",
                          headers=login_headers(client, "admin", "correct-horse-123"))
    assert response.status_code == 200
    segment = response.json()["segments"][0]
    assert segment["translated_text"] == text
    assert segment["glossary_terms"] == []
    assert len(segment["citations"]) == 1
