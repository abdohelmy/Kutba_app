from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MosqueGlossaryTerm
from app.services.glossary import (
    GlossaryEntry,
    build_glossary_entry,
    merge_glossary_entries,
)


def glossary_entries_for_mosque(db: Session, mosque_id: str) -> tuple[GlossaryEntry, ...]:
    records = db.scalars(
        select(MosqueGlossaryTerm)
        .where(MosqueGlossaryTerm.mosque_id == mosque_id)
        .order_by(MosqueGlossaryTerm.created_at, MosqueGlossaryTerm.id)
    )
    custom = tuple(
        build_glossary_entry(
            arabic_term=record.arabic_term,
            meaning=record.meaning,
            literal_translation=record.literal_translation,
            arabic_variations=record.arabic_variations,
            alternative_context_meanings=record.alternative_context_meanings,
        )
        for record in records
    )
    return merge_glossary_entries(custom)
