from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MosqueGlossaryTerm
from app.models.entities import GlobalGlossaryTerm
from app.services.glossary import (
    GlossaryEntry,
    build_glossary_entry,
    load_glossary,
    merge_glossary_entries,
)


def glossary_entries_for_mosque(db: Session, mosque_id: str) -> tuple[GlossaryEntry, ...]:
    records = db.scalars(
        select(MosqueGlossaryTerm)
        .where(
            MosqueGlossaryTerm.mosque_id == mosque_id,
            MosqueGlossaryTerm.approval_status == "APPROVED",
        )
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
    shared = tuple(
        build_glossary_entry(row.arabic_term, row.meaning, row.literal_translation)
        for row in db.scalars(
            select(GlobalGlossaryTerm)
            .where(GlobalGlossaryTerm.approval_status == "APPROVED")
            .order_by(GlobalGlossaryTerm.created_at)
        )
    )
    return merge_glossary_entries(custom, merge_glossary_entries(shared, load_glossary()))
