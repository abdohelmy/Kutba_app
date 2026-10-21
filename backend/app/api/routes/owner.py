"""Owner-only operations. Mosque admins cannot assign themselves this role."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles
from app.db.session import get_db
from app.models import Mosque, MosqueGlossaryTerm, Sermon, SermonStatus, User, UserRole
from app.models.entities import AdminAudit, GlobalGlossaryTerm
from app.services.account_email import email_ready, reset_link, send_email
from app.services.glossary import load_glossary
from app.services.glossary_contributions import global_term_key

router = APIRouter(prefix="/owner", tags=["owner"])
owner_only = require_roles(UserRole.SUPER_ADMIN)


def audit(db: Session, user: User, action: str, target: str, details: str = "") -> None:
    db.add(AdminAudit(actor_id=user.id, action=action, target_id=target, details=details))


def record(db: Session, model, identity: str):
    value = db.get(model, identity)
    if not value:
        raise HTTPException(404, "Item not found")
    return value


@router.get("/dashboard")
def dashboard(user: User = Depends(owner_only), db: Session = Depends(get_db)):
    return {
        "username": user.username,
        "contact_email": user.contact_email,
        "email_enabled": email_ready(),
        "pending_glossary": (
            db.scalar(
                select(func.count())
                .select_from(GlobalGlossaryTerm)
                .where(GlobalGlossaryTerm.approval_status == "PENDING")
            )
            + db.scalar(
                select(func.count())
                .select_from(MosqueGlossaryTerm)
                .where(MosqueGlossaryTerm.approval_status == "PENDING")
            )
        ),
        "pending": db.scalar(
            select(func.count()).select_from(Mosque).where(Mosque.approval_status == "PENDING")
        ),
        "mosques": db.scalar(select(func.count()).select_from(Mosque)),
        "translating": db.scalar(
            select(func.count())
            .select_from(Sermon)
            .where(Sermon.status == SermonStatus.TRANSLATING)
        ),
        "failed": db.scalar(
            select(func.count()).select_from(Sermon).where(Sermon.status == SermonStatus.FAILED)
        ),
    }


@router.get("/mosques")
def mosques(user: User = Depends(owner_only), db: Session = Depends(get_db)):
    return [
        {
            "id": m.id,
            "name": m.name,
            "city": m.city,
            "country": m.country,
            "is_active": m.is_active,
            "approval_status": m.approval_status,
            "admins": [
                {
                    "id": a.id,
                    "username": a.username,
                    "display_name": a.display_name,
                    "contact_email": a.contact_email,
                    "is_active": a.is_active,
                }
                for a in db.scalars(select(User).where(User.mosque_id == m.id))
            ],
        }
        for m in db.scalars(select(Mosque).order_by(Mosque.created_at.desc()))
    ]


class MosqueEdit(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    action: Literal["approve", "reject", "suspend", "restore"] | None = None


class AccountEdit(BaseModel):
    is_active: bool | None = None
    contact_email: str | None = Field(
        default=None, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$"
    )


@router.patch("/users/{user_id}")
def edit_account(
    user_id: str,
    payload: AccountEdit,
    user: User = Depends(owner_only),
    db: Session = Depends(get_db),
):
    account = record(db, User, user_id)
    if account.role == UserRole.SUPER_ADMIN:
        raise HTTPException(403, "Owner accounts cannot be disabled or edited here")
    if payload.is_active is not None:
        account.is_active = payload.is_active
        account.auth_version += 1
    if payload.contact_email is not None:
        account.contact_email = payload.contact_email
    audit(db, user, "account.update", account.id)
    db.commit()
    return {"status": "saved"}


@router.patch("/mosques/{mosque_id}")
def edit_mosque(
    mosque_id: str,
    payload: MosqueEdit,
    user: User = Depends(owner_only),
    db: Session = Depends(get_db),
):
    mosque = record(db, Mosque, mosque_id)
    if payload.name is not None:
        if len(payload.name.strip()) < 2:
            raise HTTPException(422, "Enter a mosque name")
        if db.scalar(
            select(Mosque.id).where(
                func.lower(Mosque.name) == payload.name.strip().lower(), Mosque.id != mosque_id
            )
        ):
            raise HTTPException(409, "Mosque name is already registered")
        mosque.name = payload.name.strip()
    action = payload.action
    if action and mosque.approval_status == "REMOVED":
        raise HTTPException(409, "This mosque is archived")
    if action == "restore" and mosque.approval_status != "APPROVED":
        raise HTTPException(409, "Approve the mosque first")
    if action == "suspend" and mosque.approval_status != "APPROVED":
        raise HTTPException(409, "Only approved mosques can be suspended")
    if action:
        mosque.is_active = action in {"approve", "restore"}
        if action in {"approve", "reject"}:
            mosque.approval_status = "APPROVED" if action == "approve" else "REJECTED"
        # Invalidate existing sessions on a state change, including restores.
        for admin in db.scalars(select(User).where(User.mosque_id == mosque_id)):
            admin.auth_version += 1
    audit(db, user, "mosque." + (action or "rename"), mosque_id)
    db.commit()
    return {"status": "saved"}


@router.delete("/mosques/{mosque_id}", status_code=204)
def remove_mosque(mosque_id: str, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    mosque = record(db, Mosque, mosque_id)
    # Deliberately preserve accounts and their attribution; remove public access and disable admins.
    mosque.is_active = False
    mosque.approval_status = "REMOVED"
    for admin in db.scalars(select(User).where(User.mosque_id == mosque_id)):
        admin.is_active = False
        admin.auth_version += 1
    audit(db, user, "mosque.remove", mosque_id, "Archived; sermons and attribution preserved")
    db.commit()


@router.post("/users/{user_id}/reset-link")
def issue_reset(user_id: str, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    account = record(db, User, user_id)
    if account.role == UserRole.SUPER_ADMIN and account.id != user.id:
        raise HTTPException(403, "Cannot reset another owner")
    if not account.is_active:
        raise HTTPException(409, "Account is disabled")
    link = reset_link(db, account)
    audit(db, user, "account.reset_link", account.id)
    db.commit()
    sent = bool(
        account.contact_email
        and send_email(
            account.contact_email,
            "Set your Khutba password",
            f"This link expires in 30 minutes:\n{link}",
        )
    )
    return {"link": link, "email_sent": sent, "expires_minutes": 30}


@router.get("/sermons")
def sermons(user: User = Depends(owner_only), db: Session = Depends(get_db)):
    names = {m.id: m.name for m in db.scalars(select(Mosque))}
    return [
        {
            "id": s.id,
            "title": s.title,
            "mosque_id": s.mosque_id,
            "mosque_name": names.get(s.mosque_id),
            "khutba_date": s.khutba_date,
            "target_language": s.target_language,
            "status": s.status,
            "failure_reason": s.failure_reason,
        }
        for s in db.scalars(
            select(Sermon).order_by(Sermon.khutba_date.desc(), Sermon.created_at.desc())
        )
    ]


@router.get("/audit")
def history(user: User = Depends(owner_only), db: Session = Depends(get_db)):
    return [
        {
            "id": a.id,
            "actor_id": a.actor_id,
            "action": a.action,
            "target_id": a.target_id,
            "details": a.details,
            "created_at": a.created_at,
        }
        for a in db.scalars(select(AdminAudit).order_by(AdminAudit.created_at.desc()).limit(200))
    ]


class GlossaryEdit(BaseModel):
    arabic_term: str = Field(min_length=1, max_length=250)
    literal_translation: str = Field(min_length=1, max_length=500)
    meaning: str = Field(min_length=3, max_length=4000)


@router.get("/glossary")
def glossary(user: User = Depends(owner_only), db: Session = Depends(get_db)):
    overrides = {row.normalized_term: row for row in db.scalars(select(GlobalGlossaryTerm))}
    items = {
        global_term_key(e.arabic_term): {
            "id": None,
            "arabic_term": e.arabic_term,
            "literal_translation": e.literal_translation,
            "meaning": e.meaning,
            "scope": "base",
        }
        for e in load_glossary()
    }
    for key, row in overrides.items():
        items[key] = {
            "id": row.id,
            "arabic_term": row.arabic_term,
            "literal_translation": row.literal_translation,
            "meaning": row.meaning,
            "scope": "global",
            "approval_status": row.approval_status,
        }
    names = {m.id: m.name for m in db.scalars(select(Mosque))}
    contributors = {u.id: names.get(u.mosque_id, u.display_name) for u in db.scalars(select(User))}
    for row in overrides.values():
        items[row.normalized_term]["submitted_by"] = contributors.get(row.created_by, "App owner")
    return {
        "global": list(items.values()),
        "mosque": [
            {
                "id": row.id,
                "mosque_id": row.mosque_id,
                "mosque_name": names.get(row.mosque_id),
                "arabic_term": row.arabic_term,
                "literal_translation": row.literal_translation,
                "meaning": row.meaning,
                "scope": "mosque",
                "approval_status": row.approval_status,
                "arabic_variations": row.arabic_variations,
                "alternative_context_meanings": row.alternative_context_meanings,
            }
            for row in db.scalars(select(MosqueGlossaryTerm))
        ],
    }


@router.put("/glossary")
def save_glossary(
    payload: GlossaryEdit, user: User = Depends(owner_only), db: Session = Depends(get_db)
):
    key = global_term_key(payload.arabic_term)
    if not key or not payload.literal_translation.strip() or not payload.meaning.strip():
        raise HTTPException(422, "Complete all glossary fields")
    row = db.scalar(select(GlobalGlossaryTerm).where(GlobalGlossaryTerm.normalized_term == key))
    if not row:
        row = GlobalGlossaryTerm(normalized_term=key, created_by=user.id)
        db.add(row)
    row.arabic_term = payload.arabic_term.strip()
    row.literal_translation = payload.literal_translation.strip()
    row.meaning = payload.meaning.strip()
    row.approval_status = "APPROVED"
    audit(db, user, "glossary.save", key)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Term changed; refresh and try again") from None
    return {"status": "saved"}


class GlossaryApproval(BaseModel):
    action: Literal["approve", "reject"]


@router.patch("/glossary/{scope}/{term_id}")
def review_glossary(
    scope: Literal["global", "mosque"],
    term_id: str,
    payload: GlossaryApproval,
    user: User = Depends(owner_only),
    db: Session = Depends(get_db),
):
    row = record(db, GlobalGlossaryTerm if scope == "global" else MosqueGlossaryTerm, term_id)
    row.approval_status = "APPROVED" if payload.action == "approve" else "REJECTED"
    audit(db, user, "glossary." + payload.action + "." + scope, term_id)
    db.commit()
    return {"status": "saved"}


@router.delete("/glossary/{scope}/{term_id}", status_code=204)
def delete_glossary(
    scope: Literal["global", "mosque"],
    term_id: str,
    user: User = Depends(owner_only),
    db: Session = Depends(get_db),
):
    row = record(db, GlobalGlossaryTerm if scope == "global" else MosqueGlossaryTerm, term_id)
    audit(db, user, "glossary.delete." + scope, term_id)
    db.delete(row)
    db.commit()
