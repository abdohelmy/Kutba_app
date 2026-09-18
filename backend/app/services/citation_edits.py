"""Re-anchor saved quotations after a human edit without guessing a new source."""

import re
from difflib import SequenceMatcher

REVIEW_PREFIX = "Citation review: "


def reanchor_citations(
    original: str, edited: str, citations: list[dict[str, object]]
) -> tuple[list[dict[str, object]], list[str]]:
    blocks = SequenceMatcher(None, original, edited, autojunk=False).get_matching_blocks()
    result = []
    issues = []
    used: set[tuple[str, int, int]] = set()
    for source in citations:
        citation = dict(source)
        excerpt = str(citation.get("excerpt") or "")
        start, end = citation.get("translation_start"), citation.get("translation_end")
        span = None
        if (
            isinstance(start, int)
            and isinstance(end, int)
            and 0 <= start < end <= len(original)
            and original[start:end] == excerpt
        ):
            for block in blocks:
                if block.a <= start and end <= block.a + block.size:
                    span = (block.b + start - block.a, block.b + end - block.a)
                    break
        elif excerpt:
            # Older records can be recovered only when their wording has one clear location.
            matches = list(re.finditer(re.escape(excerpt), edited))
            if len(matches) == 1:
                span = matches[0].span()
        identity = str(citation.get("chunk_id", ""))
        if span and (identity, *span) in used:
            span = None
        if span:
            used.add((identity, *span))
        citation["translation_start"] = span[0] if span else None
        citation["translation_end"] = span[1] if span else None
        citation["anchor_valid"] = span is not None
        if not span:
            label = citation.get("display_reference") or citation.get("title") or "source"
            issues.append(
                f"{REVIEW_PREFIX}{label} no longer matches its quoted wording. "
                "Restore the source quotation before approving this section."
            )
        result.append(citation)
    return result, list(dict.fromkeys(issues))
