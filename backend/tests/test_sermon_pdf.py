from datetime import UTC, date, datetime
from io import BytesIO

from pypdf import PdfReader

from app.models import SermonStatus
from app.schemas.content import (
    CitationResponse,
    GlossaryTermResponse,
    ReaderSegmentResponse,
    ReaderSermonDetailResponse,
)
from app.services.sermon_pdf import (
    _number_segment_citations,
    _register_fonts,
    _render_segment_paragraphs,
    _wrapped_arabic_lines,
    build_sermon_pdf,
)


def test_pdf_contains_numbered_references_arabic_appendix_and_source_links():
    sermon = ReaderSermonDetailResponse(
        id="sermon-1",
        mosque_id="mosque-1",
        title="Friday Khutba",
        khutba_date=date(2026, 8, 14),
        target_language="en",
        status=SermonStatus.PUBLISHED,
        provider_name="openai",
        model_name="test-model",
        failure_reason=None,
        published_at=datetime.now(UTC),
        segments=[
            ReaderSegmentResponse(
                id="segment-1",
                ordinal=0,
                translated_text=(
                    "All praise is due to Allah. God-consciousness protects the believer."
                ),
                citations=[
                    CitationResponse(
                        chunk_id="canonical:quran:1:2",
                        source_id="quran.com:1:2",
                        title="Qur'an 1:2 — Saheeh International",
                        authority="Quran.com",
                        excerpt="All praise is due to Allah, Lord of the worlds.",
                        arabic_excerpt="الْحَمْدُ لِلَّهِ رَبِّ الْعَالَمِينَ",
                        transliteration="Al-hamdu lillahi rabbi al-alamin",
                        display_reference="Al-Fatihah 1:2",
                        source_kind="quran",
                        url="https://quran.com/1/2",
                    )
                ],
                glossary_terms=[
                    GlossaryTermResponse(
                        arabic_term="التقوى",
                        meaning="Awareness of Allah that leads to obedience.",
                        literal_translation="protective awareness",
                        display_term="God-consciousness",
                    )
                ],
            )
        ],
    )

    pdf = build_sermon_pdf(sermon, "Central Mosque")
    assert pdf.startswith(b"%PDF-")

    reader = PdfReader(BytesIO(pdf))
    extracted_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "All praise is due to Allah" in extracted_text
    assert "Sources and glossary" in extracted_text
    assert "Open canonical source" in extracted_text

    annotations = [
        annotation.get_object()
        for page in reader.pages
        for annotation in (page.get("/Annots") or [])
    ]
    assert not any(annotation.get("/Subtype") == "/Text" for annotation in annotations)
    assert "Interactive notes" not in extracted_text
    assert "Each numbered source below" in extracted_text
    assert any(
        annotation.get("/A", {}).get("/URI") == "https://quran.com/1/2"
        for annotation in annotations
        if annotation.get("/Subtype") == "/Link"
    )


def test_reference_number_is_inserted_after_closing_quote():
    text = 'The Prophet said: “Actions are by intentions.” Then he continued.'
    excerpt = "Actions are by intentions."
    start = text.index(excerpt)
    citation = CitationResponse(
        chunk_id="canonical:hadith:bukhari:1",
        source_id="sunnah.com:bukhari:1",
        title="Sahih al-Bukhari 1",
        authority="Sunnah.com",
        excerpt=excerpt,
        arabic_excerpt="إِنَّمَا الأَعْمَالُ بِالنِّيَّاتِ",
        source_kind="hadith",
        url="https://sunnah.com/bukhari:1",
        translation_start=start,
        translation_end=start + len(excerpt),
    )

    numbered = _number_segment_citations(text, [citation], 1)
    closing_quote_end = text.index("”") + 1
    assert numbered[0].position == closing_quote_end

    rendered = "".join(
        _render_segment_paragraphs(text, numbered, "KhutbaSansBold", "KhutbaArabic")
    )
    marker_position = rendered.index("backColor")
    assert rendered.index("intentions.”") < marker_position < rendered.index("Then he continued")


def test_overlapping_verse_wording_uses_the_later_occurrence_for_the_later_source():
    first_excerpt = "Tell the believing men to lower their gaze and guard their chastity"
    repeated_excerpt = "to lower their gaze and guard their chastity"
    text = (
        f'“{first_excerpt}.” And: “Tell the believing women '
        f'{repeated_excerpt} and not reveal their adornments.”'
    )
    first_start = text.index(first_excerpt)
    wrong_repeated_start = text.index(repeated_excerpt)
    citations = [
        CitationResponse(
            chunk_id="quran:24:30",
            source_id="quran.com:24:30",
            title="Qur'an 24:30",
            authority="Quran.com",
            excerpt=first_excerpt,
            source_kind="quran",
            translation_start=first_start,
            translation_end=first_start + len(first_excerpt),
        ),
        CitationResponse(
            chunk_id="quran:24:31",
            source_id="quran.com:24:31",
            title="Qur'an 24:31",
            authority="Quran.com",
            excerpt=repeated_excerpt,
            source_kind="quran",
            translation_start=wrong_repeated_start,
            translation_end=wrong_repeated_start + len(repeated_excerpt),
        ),
    ]

    numbered = _number_segment_citations(text, citations, 1)
    later_occurrence_end = text.rindex(repeated_excerpt) + len(repeated_excerpt)
    assert numbered[0].citation.source_id == "quran.com:24:30"
    assert numbered[1].citation.source_id == "quran.com:24:31"
    assert numbered[1].position >= later_occurrence_end


def test_long_arabic_source_wraps_without_reversing_line_order():
    _regular_font, _bold_font, arabic_font = _register_fonts()
    arabic = (
        "قَالَ رَسُولُ اللَّهِ عَلَيْكُمْ بِالصِّدْقِ فَإِنَّ الصِّدْقَ يَهْدِي إِلَى الْبِرِّ "
        "وَإِنَّ الْبِرَّ يَهْدِي إِلَى الْجَنَّةِ"
    )

    lines = _wrapped_arabic_lines(arabic, arabic_font, 13, 180)
    assert len(lines) > 1
    assert " ".join(lines) == " ".join(arabic.split())
    assert lines[0].startswith("قَالَ رَسُولُ")
