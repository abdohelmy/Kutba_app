from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape
from io import BytesIO
from pathlib import Path

from arabic_reshaper import ArabicReshaper
from bidi.algorithm import get_display
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer

from app.schemas.content import CitationResponse, GlossaryTermResponse, ReaderSermonDetailResponse

BRAND_GREEN = colors.HexColor("#096B50")
INK = colors.HexColor("#17231F")
MUTED = colors.HexColor("#61706A")
RULE = colors.HexColor("#D6E2DD")

SOURCE_MARKER_RE = re.compile(r"\s*\[S:[^\]\r\n]+\]")
TOKEN_RE = re.compile(r"[\w]+(?:[’'][\w]+)*", re.UNICODE)
TRAILING_CITATION_PUNCTUATION = frozenset(".،,؛;:!?؟\"'”’)]}")
ARABIC_RUN_RE = re.compile(
    r"[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\ufb50-\ufdff\ufe70-\ufeff]+"
    r"(?:[ \t]+(?=[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\ufb50-\ufdff\ufe70-\ufeff]))*"
)
ARABIC_RESHAPER = ArabicReshaper(
    configuration={
        "delete_harakat": False,
        "shift_harakat_position": True,
        "support_ligatures": True,
    }
)


@dataclass(frozen=True)
class TextToken:
    normalized: str
    end: int


@dataclass(frozen=True)
class NumberedCitation:
    number: int
    position: int
    citation: CitationResponse


def _register_fonts() -> tuple[str, str, str]:
    """Register fonts bundled with the service so every deployment renders identically."""
    font_dir = Path(__file__).resolve().parents[1] / "assets" / "fonts"
    regular_path = font_dir / "NotoSans-Regular.ttf"
    bold_path = font_dir / "NotoSans-Bold.ttf"
    arabic_path = font_dir / "NotoNaskhArabic.ttf"
    missing = [path.name for path in (regular_path, bold_path, arabic_path) if not path.is_file()]
    if missing:
        raise RuntimeError(f"Bundled PDF fonts are missing: {', '.join(missing)}")
    if "KhutbaSans" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("KhutbaSans", str(regular_path)))
    if "KhutbaSansBold" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("KhutbaSansBold", str(bold_path)))
    if "KhutbaArabic" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("KhutbaArabic", str(arabic_path), shapable=False))
    return "KhutbaSans", "KhutbaSansBold", "KhutbaArabic"


def _sanitized_reader_text(value: str) -> str:
    value = SOURCE_MARKER_RE.sub("", value)
    value = re.sub(r"[ \t]+([,.;:!?])", r"\1", value)
    value = re.sub(r"[ \t]{2,}", " ", value)
    return value.strip()


def _tokens(value: str) -> list[TextToken]:
    return [
        TextToken(match.group(0).casefold(), match.end())
        for match in TOKEN_RE.finditer(value)
    ]


def _partial_insertion_point(
    text: str,
    excerpt: str,
    used: set[int],
    minimum_position: int,
) -> int | None:
    text_tokens = _tokens(text)
    excerpt_tokens = _tokens(excerpt)
    candidates: list[tuple[int, int]] = []
    for text_start in range(len(text_tokens)):
        for excerpt_start in range(len(excerpt_tokens)):
            if text_tokens[text_start].normalized != excerpt_tokens[excerpt_start].normalized:
                continue
            run = 0
            while (
                text_start + run < len(text_tokens)
                and excerpt_start + run < len(excerpt_tokens)
                and text_tokens[text_start + run].normalized
                == excerpt_tokens[excerpt_start + run].normalized
            ):
                run += 1
            if run >= 4:
                candidates.append((run, text_tokens[text_start + run - 1].end))
    for _length, end in sorted(candidates, reverse=True):
        if end >= minimum_position and end not in used:
            return end
    return None


def _candidate_excerpts(excerpt: str) -> list[str]:
    edge_punctuation = " \n\r\t\"'“”‘’.,;:!?-"
    values = [excerpt, *re.split(r"(?<=[.!?])\s+", excerpt)]
    return sorted(
        {
            value.strip(edge_punctuation)
            for value in values
            if len(value.strip(edge_punctuation)) >= 12
        },
        key=len,
        reverse=True,
    )


def _citation_insertion_point(
    text: str,
    citation: CitationResponse,
    used: set[int],
    minimum_position: int,
) -> int | None:
    start = citation.translation_start
    end = citation.translation_end
    if (
        start is not None
        and end is not None
        and start >= 0
        and start >= minimum_position
        and start < end <= len(text)
        and text[start:end].casefold() == citation.excerpt.casefold()
        and end not in used
    ):
        return end

    for candidate in _candidate_excerpts(citation.excerpt):
        matches = list(re.finditer(re.escape(candidate), text, flags=re.IGNORECASE))
        for match in matches:
            if match.start() >= minimum_position and match.end() not in used:
                return match.end()
    return _partial_insertion_point(text, citation.excerpt, used, minimum_position)


def _after_closing_punctuation(text: str, position: int) -> int:
    while position < len(text) and text[position] in TRAILING_CITATION_PUNCTUATION:
        position += 1
    return position


def _number_segment_citations(
    text: str,
    citations: list[CitationResponse],
    first_number: int,
) -> list[NumberedCitation]:
    used: set[int] = set()
    positioned: list[tuple[int, int, CitationResponse]] = []
    minimum_position = 0
    for original_index, citation in enumerate(citations):
        if citation.source_kind not in {"quran", "hadith"}:
            continue
        raw_position = _citation_insertion_point(
            text,
            citation,
            used,
            minimum_position,
        )
        if raw_position is None and minimum_position:
            raw_position = _citation_insertion_point(text, citation, used, 0)
        if raw_position is None:
            raw_position = len(text)
        used.add(raw_position)
        minimum_position = max(minimum_position, raw_position)
        position = _after_closing_punctuation(text, raw_position)
        positioned.append((position, original_index, citation))
    positioned.sort(key=lambda item: (item[0], item[1]))
    return [
        NumberedCitation(first_number + index, position, citation)
        for index, (position, _original_index, citation) in enumerate(positioned)
    ]


def _marker_html(number: int, bold_font: str) -> str:
    return (
        f'&#160;<super><font name="{bold_font}" size="7" color="#FFFFFF" '
        f'backColor="#096B50">&#160;&#160;{number}&#160;&#160;</font></super>'
    )


def _display_arabic(value: str) -> str:
    logical_text = value.replace("\u200f", "")
    return get_display(ARABIC_RESHAPER.reshape(logical_text), base_dir="R")


def _escape_mixed_text(value: str, arabic_font: str) -> str:
    parts: list[str] = []
    cursor = 0
    for match in ARABIC_RUN_RE.finditer(value):
        parts.append(escape(value[cursor : match.start()]))
        parts.append(
            f'<font name="{arabic_font}">{escape(_display_arabic(match.group(0)))}</font>'
        )
        cursor = match.end()
    parts.append(escape(value[cursor:]))
    return "".join(parts)


def _render_segment_paragraphs(
    text: str,
    citations: list[NumberedCitation],
    bold_font: str,
    arabic_font: str,
) -> list[str]:
    events: dict[int, list[NumberedCitation]] = {}
    for citation in citations:
        events.setdefault(citation.position, []).append(citation)
    parts: list[str] = []
    cursor = 0
    for position in sorted(events):
        safe_position = min(max(position, cursor), len(text))
        chunk = text[cursor:safe_position]
        markers = "".join(_marker_html(item.number, bold_font) for item in events[position])
        tail = re.search(r"\S+$", chunk)
        if tail:
            parts.append(_escape_mixed_text(chunk[: tail.start()], arabic_font))
            parts.append("<nobr>")
            parts.append(_escape_mixed_text(chunk[tail.start() :], arabic_font))
            parts.append(markers)
            parts.append("</nobr>")
        else:
            parts.append(_escape_mixed_text(chunk, arabic_font))
            parts.append(markers)
        cursor = safe_position
    parts.append(_escape_mixed_text(text[cursor:], arabic_font))
    marked_text = "".join(parts)
    return [
        paragraph.replace("\n", "<br/>")
        for paragraph in re.split(r"\n\s*\n", marked_text)
        if paragraph.strip()
    ]


def _wrapped_arabic_lines(
    value: str,
    font_name: str,
    font_size: float,
    maximum_width: float,
) -> list[str]:
    lines: list[str] = []
    for logical_line in value.replace("\u200f", "").splitlines() or [""]:
        words = logical_line.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            display_candidate = _display_arabic(candidate)
            if pdfmetrics.stringWidth(display_candidate, font_name, font_size) <= maximum_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def _arabic_paragraph(
    value: str,
    arabic_style: ParagraphStyle,
    arabic_font: str,
    maximum_width: float,
) -> Paragraph:
    rendered_lines = [
        escape(_display_arabic(line))
        for line in _wrapped_arabic_lines(
            value,
            arabic_font,
            arabic_style.fontSize,
            maximum_width,
        )
    ]
    return Paragraph("<br/>".join(rendered_lines), arabic_style)


def build_sermon_pdf(sermon: ReaderSermonDetailResponse, mosque_name: str) -> bytes:
    regular_font, bold_font, arabic_font = _register_fonts()
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=19 * mm,
        rightMargin=19 * mm,
        topMargin=22 * mm,
        bottomMargin=20 * mm,
        title=sermon.title,
        author=mosque_name,
        subject="English khutba translation with numbered canonical references",
    )
    base = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "KhutbaTitle",
        parent=base["Title"],
        fontName=bold_font,
        fontSize=22,
        leading=28,
        textColor=BRAND_GREEN,
        alignment=TA_CENTER,
        spaceAfter=8,
    )
    metadata_style = ParagraphStyle(
        "Metadata",
        parent=base["Normal"],
        fontName=regular_font,
        fontSize=9,
        leading=13,
        textColor=MUTED,
        alignment=TA_CENTER,
        spaceAfter=12,
    )
    section_style = ParagraphStyle(
        "Section",
        parent=base["Heading2"],
        fontName=bold_font,
        fontSize=15,
        leading=19,
        textColor=BRAND_GREEN,
        spaceBefore=8,
        spaceAfter=8,
    )
    body_style = ParagraphStyle(
        "KhutbaBody",
        parent=base["BodyText"],
        fontName=regular_font,
        fontSize=11,
        leading=17,
        textColor=INK,
        alignment=TA_LEFT,
        spaceAfter=7,
    )
    small_style = ParagraphStyle(
        "Small",
        parent=body_style,
        fontSize=8.5,
        leading=12,
        textColor=MUTED,
        spaceAfter=4,
    )
    appendix_style = ParagraphStyle(
        "Appendix",
        parent=body_style,
        fontSize=9.5,
        leading=14,
        leftIndent=7,
        borderColor=RULE,
        borderWidth=0.5,
        borderPadding=7,
        backColor=colors.HexColor("#F7FAF9"),
        spaceAfter=5,
    )
    arabic_style = ParagraphStyle(
        "Arabic",
        parent=appendix_style,
        fontName=arabic_font,
        fontSize=12.5,
        leading=19.5,
        alignment=TA_RIGHT,
    )
    arabic_text_width = document.width - 28

    story = [
        Paragraph(_escape_mixed_text(sermon.title, arabic_font), title_style),
        Paragraph(
            _escape_mixed_text(
                f"{mosque_name}  |  {sermon.khutba_date.isoformat()}  |  "
                f"{sermon.target_language.upper()}",
                arabic_font,
            ),
            metadata_style,
        ),
        Paragraph(
            "This download contains the reviewed English translation. Numbered squares "
            "after Qur'an verses and hadiths refer to the sources section at the end.",
            small_style,
        ),
        Spacer(1, 5),
    ]

    next_citation_number = 1
    all_citations: list[NumberedCitation] = []
    all_glossary: list[GlossaryTermResponse] = []
    for segment in sermon.segments:
        reader_text = _sanitized_reader_text(segment.translated_text)
        numbered = _number_segment_citations(
            reader_text,
            segment.citations,
            next_citation_number,
        )
        next_citation_number += len(numbered)
        all_citations.extend(numbered)
        all_glossary.extend(segment.glossary_terms)
        for rendered_paragraph in _render_segment_paragraphs(
            reader_text,
            numbered,
            bold_font,
            arabic_font,
        ):
            story.append(Paragraph(rendered_paragraph, body_style))

    if all_citations or all_glossary:
        story.extend(
            [
                PageBreak(),
                Paragraph("Sources and glossary", title_style),
                Paragraph(
                    "Each numbered source below matches the square carrying the same number "
                    "in the sermon.",
                    small_style,
                ),
            ]
        )

    if all_citations:
        story.append(Paragraph("Qur'an and hadith sources", section_style))
        for numbered in all_citations:
            citation = numbered.citation
            reference = citation.display_reference or citation.title
            kind = "Qur'an" if citation.source_kind == "quran" else "Hadith"
            details = [
                f"{_marker_html(numbered.number, bold_font)} <b>{kind}: "
                f"{escape(reference)}</b>",
                f"<br/><b>Canonical English:</b> {escape(citation.excerpt)}",
            ]
            if citation.transliteration:
                details.append(
                    f"<br/><b>English transliteration:</b> {escape(citation.transliteration)}"
                )
            if citation.url:
                safe_url = escape(citation.url, quote=True)
                details.append(
                    f'<br/><link href="{safe_url}" color="#235FA4">Open canonical source</link>'
                )
            block = [Paragraph("".join(details), appendix_style)]
            if citation.arabic_excerpt:
                block.append(
                    _arabic_paragraph(
                        citation.arabic_excerpt,
                        arabic_style,
                        arabic_font,
                        arabic_text_width,
                    )
                )
            story.append(KeepTogether(block))

    if all_glossary:
        story.append(Paragraph("Glossary", section_style))
        for term in all_glossary:
            details = (
                f"<b>{escape(term.display_term)}</b>"
                f"<br/><b>Meaning:</b> {escape(term.meaning)}"
            )
            if term.literal_translation:
                details += f"<br/><b>Literal translation:</b> {escape(term.literal_translation)}"
            if term.alternative_context_meanings:
                details += (
                    f"<br/><b>Other contexts:</b> "
                    f"{escape(term.alternative_context_meanings)}"
                )
            story.append(
                KeepTogether(
                    [
                        Paragraph(details, appendix_style),
                        _arabic_paragraph(
                            term.arabic_term,
                            arabic_style,
                            arabic_font,
                            arabic_text_width,
                        ),
                    ]
                )
            )

    def decorate_page(canvas: Canvas, doc: SimpleDocTemplate) -> None:
        canvas.saveState()
        canvas.setStrokeColor(RULE)
        canvas.line(document.leftMargin, 14 * mm, A4[0] - document.rightMargin, 14 * mm)
        canvas.setFont(regular_font, 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(document.leftMargin, 9 * mm, "Khutba - reviewed English translation")
        canvas.drawRightString(A4[0] - document.rightMargin, 9 * mm, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=decorate_page, onLaterPages=decorate_page)
    return buffer.getvalue()
