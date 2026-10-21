"""Validate popup wording against the exact Arabic-note occurrence in the translation."""
import re

from pydantic import BaseModel, Field


class GlossaryPhrase(BaseModel):
    arabic_term: str = Field(min_length=1)
    phrase: str = Field(min_length=1)
    arabic_occurrence: int = Field(default=0, ge=0)


def phrase_at_note(preceding: str, phrase: str) -> str:
    """Copy the rendered phrase, rejecting stale metadata and partial-word matches."""
    phrase = phrase.strip()
    if not phrase:
        return ''
    pattern = r'(?<!\w)' + r'\s+'.join(re.escape(word) for word in phrase.split()) + r'\s*$'
    match = re.search(pattern, preceding, re.IGNORECASE)
    return match.group().rstrip() if match else ''
