import base64
import hashlib
import io
import time
import wave
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, UploadFile
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.dependencies import bearer_scheme, require_mosque_admin, require_roles
from app.api.routes.admin import load_admin_sermon
from app.api.routes.owner import audit
from app.api.routes.reader import _published_sermon
from app.db.session import get_db
from app.models import Sermon, SermonStatus, User, UserRole
from app.models.entities import LiveWorkerToken
from app.services import live_sessions as live
from app.services.live_matcher import LiveMatcher

router = APIRouter(tags=["live"])


def base_sermon(db: Session, sermon: Sermon) -> Sermon:
    base = db.get(Sermon, sermon.english_sermon_id) if sermon.english_sermon_id else sermon
    if base is None or base.status != SermonStatus.PUBLISHED:
        raise HTTPException(409, "Publish the English khutba before going live")
    return base


def valid_session(base: Sermon) -> live.LiveSession | None:
    session = live.session_for(base.id)
    if session and session.revision != live.sermon_revision(base):
        del live.SESSIONS[base.id]
        return None
    return session


def admin_state(sermon: Sermon, base: Sermon) -> dict:
    valid_session(base)
    return dict(
        live.public_state(sermon, base.id),
        worker_ready=live.worker_ready(),
        mapping_ready=live.mapping_ready(sermon),
        preparing=base.id in live.PREPARING,
        preparation_error=live.ERRORS.get(base.id),
        audio_sequence=live.SESSIONS[base.id].sequence if base.id in live.SESSIONS else -1,
    )


@router.get("/admin/sermons/{sermon_id}/live")
async def live_admin_status(
    sermon_id: str,
    background: BackgroundTasks,
    session_id: str | None = None,
    user: User = Depends(require_mosque_admin),
    db: Session = Depends(get_db),
):
    sermon = load_admin_sermon(db, user, sermon_id)
    base = base_sermon(db, sermon)
    async with live.LOCK:
        # Old publications and interrupted preparations recover when their admin
        # opens this screen. Failed attempts require a deliberate retry, not polling.
        if (not live.mapping_ready(sermon) or not live.mapping_ready(base)) and base.id not in live.ERRORS:
            live.queue_preparation(background, base.id)
        session = valid_session(base)
        if session and session.identity == session_id:
            session.touched = time.monotonic()
        return admin_state(sermon, base)


@router.post("/admin/sermons/{sermon_id}/live/prepare", status_code=202)
async def prepare_live(
    sermon_id: str,
    background: BackgroundTasks,
    user: User = Depends(require_mosque_admin),
    db: Session = Depends(get_db),
):
    sermon = load_admin_sermon(db, user, sermon_id)
    base = base_sermon(db, sermon)
    async with live.LOCK:
        live.queue_preparation(background, base.id)
    return {"status": "preparing"}


class SessionAction(BaseModel):
    action: Literal["start", "pause", "resume", "stop"]
    session_id: str | None = None


@router.post("/admin/sermons/{sermon_id}/live")
async def control_live(
    sermon_id: str,
    payload: SessionAction,
    user: User = Depends(require_mosque_admin),
    db: Session = Depends(get_db),
):
    sermon = load_admin_sermon(db, user, sermon_id)
    base = base_sermon(db, sermon)
    async with live.LOCK:
        session = valid_session(base)
        if payload.action == "start":
            if session:
                raise HTTPException(
                    409, "A live session already exists. Stop it before starting another."
                )
            if not live.worker_ready():
                raise HTTPException(503, "The Windows speech worker is offline")
            if not live.mapping_ready(sermon) or not live.mapping_ready(base):
                raise HTTPException(409, "Live highlighting is preparing. Wait a moment and try again.")
            if len(live.SESSIONS) >= live.MAX_SESSIONS:
                raise HTTPException(429, "Live tracking is at capacity. Try again later.")
            if any(s.mosque_id == base.mosque_id for s in live.SESSIONS.values()):
                raise HTTPException(409, "This mosque is already live on another khutba")
            session = live.LiveSession(
                base.id,
                base.mosque_id,
                live.sermon_revision(base),
                LiveMatcher(
                    [(str(s.ordinal), s.arabic_text) for s in base.segments],
                    {str(s.ordinal): [(link["arabic_start"], link["arabic_end"])
                                      for link in s.live_alignment.get("links", [])]
                     for s in base.segments},
                ),
            )
            live.SESSIONS[base.id] = session
        else:
            if session is None or payload.session_id != session.identity:
                raise HTTPException(409, "The live session changed. Refresh this page.")
            live.reset_session_buffers(session)
            session.touched = time.monotonic()
            if payload.action == "stop":
                del live.SESSIONS[base.id]
            elif payload.action == "pause":
                session.paused = True
            else:
                if not live.worker_ready():
                    raise HTTPException(503, "The Windows speech worker is offline")
                session.paused = False
    return admin_state(sermon, base)


@router.post("/admin/sermons/{sermon_id}/live/audio", status_code=202)
async def upload_audio(
    sermon_id: str,
    session_id: str,
    sequence: int,
    file: UploadFile,
    kind: Literal["full", "quick"] = "full",
    user: User = Depends(require_mosque_admin),
    db: Session = Depends(get_db),
):
    sermon = load_admin_sermon(db, user, sermon_id)
    base = base_sermon(db, sermon)
    audio = await file.read(live.MAX_AUDIO_BYTES + 1)
    await file.close()
    try:
        live.validate_wav(audio)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    async with live.LOCK:
        session = valid_session(base)
        if session is None or session.identity != session_id or session.paused:
            raise HTTPException(409, "This live session is not recording")
        if not live.worker_ready():
            raise HTTPException(
                503, "The speech worker disconnected. Pause recording and reconnect it."
            )
        if sequence < 0 or sequence <= session.sequence:
            raise HTTPException(409, "Audio sequence is stale")
        now = time.monotonic()
        if now - session.audio_received < 1:
            raise HTTPException(429, "Audio chunks are arriving too quickly")
        session.sequence = sequence
        session.audio_received = session.touched = now
        # Short checks only supplement an established position. Never queue them
        # behind a full check, or let old short checks delay the next full one.
        if kind == "quick" and (session.matcher.position is None or any(
            not j.claimed_by and j.kind == "full" for j in session.jobs
        )):
            return {"status": "skipped"}
        session.jobs[:] = [j for j in session.jobs if j.claimed_by or j.kind != "quick"]
        # Keep at most one claimed and two queued chunks, dropping oldest backlog.
        session.jobs[:] = [j for j in session.jobs if j.claimed_by or now - j.created < 20]
        waiting = [j for j in session.jobs if not j.claimed_by]
        if len(waiting) >= 2:
            session.jobs.remove(waiting[0])
        session.jobs.append(live.AudioJob(sequence, audio, kind=kind))
    return {"status": "queued"}


@router.get("/reader/sermons/{sermon_id}/live")
async def reader_live(sermon_id: str, db: Session = Depends(get_db)):
    sermon = _published_sermon(sermon_id, db)
    base = base_sermon(db, sermon)
    async with live.LOCK:
        valid_session(base)
        return live.public_state(sermon, base.id)


def get_worker(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> LiveWorkerToken:
    if credentials is None:
        raise HTTPException(401, "Speech worker authentication required")
    digest = hashlib.sha256(credentials.credentials.encode()).hexdigest()
    token = db.scalar(
        select(LiveWorkerToken).where(
            LiveWorkerToken.token_hash == digest,
            LiveWorkerToken.is_active.is_(True),
            LiveWorkerToken.expires_at > datetime.now(UTC).replace(tzinfo=None),
        )
    )
    owner = db.get(User, token.created_by) if token else None
    if not token or not owner or not owner.is_active or owner.role != UserRole.SUPER_ADMIN:
        raise HTTPException(401, "Speech worker token is invalid or expired")
    return token


@router.post("/owner/live-worker-token")
async def issue_worker_token(
    user: User = Depends(require_roles(UserRole.SUPER_ADMIN)), db: Session = Depends(get_db)
):
    import secrets

    value = secrets.token_urlsafe(32)
    db.execute(update(LiveWorkerToken).values(is_active=False))
    db.add(
        LiveWorkerToken(
            token_hash=hashlib.sha256(value.encode()).hexdigest(),
            expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30),
            created_by=user.id,
        )
    )
    audit(db, user, "live.worker_token_issued", "speech-worker")
    db.commit()
    live.WORKERS.clear()
    return {"token": value, "expires_days": 30}


@router.delete("/owner/live-worker-token", status_code=204)
async def revoke_worker(
    user: User = Depends(require_roles(UserRole.SUPER_ADMIN)), db: Session = Depends(get_db)
):
    db.execute(update(LiveWorkerToken).values(is_active=False))
    audit(db, user, "live.worker_token_revoked", "speech-worker")
    db.commit()
    live.WORKERS.clear()


@router.get("/live-worker/job")
async def next_job(worker: LiveWorkerToken = Depends(get_worker), semantic_shadow: bool = False):
    live.WORKERS[worker.id] = time.monotonic()
    async with live.LOCK:
        live.clean_sessions()
        candidates = [
            (s, j)
            for s in live.SESSIONS.values()
            if not s.paused and not any(j.claimed_by for j in s.jobs)
            for j in s.jobs
            if not j.claimed_by
        ]
        if not candidates:
            return Response(status_code=204)
        session, job = min(candidates, key=lambda item: item[1].created)
        job.claimed_by = worker.id
        job.claimed_at = time.monotonic()
        return {
            "session_id": session.identity,
            "job_id": job.identity,
            "sequence": job.sequence,
            "kind": job.kind,
            "supports_unscored_candidates": True,
            "audio_base64": base64.b64encode(job.audio).decode(),
            "references": session.matcher.references() if job.kind == "full" else [],
            # Only explicitly opted-in local debug workers need this corpus.
            # It never participates in the authoritative matching decision.
            **({"semantic_passages": [
                {"index": i, "text": text}
                for i, (_, _, text) in enumerate(session.matcher.sentences)
            ]} if semantic_shadow and job.kind == "full" else {}),
            "verify_unprompted": job.kind == "full" and (
                session.matcher.position is None or session.matcher.pending is not None
                or session.matcher.state != "matched"
            ),
        }


class TranscriptCandidate(BaseModel):
    reference: Literal["current", "next", "none"]
    text: str = Field(max_length=4000)
    avg_logprob: float | None = Field(default=None, ge=-100, le=0, allow_inf_nan=False)
    no_speech_prob: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    compression_ratio: float = Field(ge=0, le=100, allow_inf_nan=False)


class TranscriptResult(BaseModel):
    session_id: str = Field(max_length=100)
    job_id: str = Field(max_length=100)
    text: str = Field(default="", max_length=4000)
    candidates: list[TranscriptCandidate] | None = Field(default=None, min_length=1, max_length=3)
    debug: bool = False


@router.post("/live-worker/result")
async def accept_result(
    payload: TranscriptResult,
    worker: LiveWorkerToken = Depends(get_worker),
    db: Session = Depends(get_db),
):
    async with live.LOCK:
        live.clean_sessions()
        session = next(
            (s for s in live.SESSIONS.values() if s.identity == payload.session_id), None
        )
        job = (
            next((j for j in session.jobs if j.identity == payload.job_id), None)
            if session
            else None
        )
        if session is None or job is None or session.paused or job.claimed_by != worker.id:
            raise HTTPException(409, "This audio job expired or the session changed")
        session.jobs.remove(job)
        age = time.monotonic() - job.created
        session.matcher.audio_end = job.created
        with wave.open(io.BytesIO(job.audio)) as audio:
            session.matcher.audio_duration = audio.getnframes() / audio.getframerate()
        matched = None
        if age > (8 if job.kind == "quick" else 16):
            session.matcher.last_diagnostic = {"reason": "delayed_audio_ignored", "sequence": job.sequence}
        elif job.kind == "quick":
            matched = session.matcher.update_quick(
                [item.model_dump() for item in payload.candidates] if payload.candidates else [],
                job.sequence,
            )
        elif payload.candidates is not None:
            matched = session.matcher.update_alternatives([item.model_dump() for item in payload.candidates], job.sequence)
        else:
            matched = session.matcher.update(payload.text, job.sequence)
        observed = live.record_passage(session, job.sequence) if matched else None
        session.matcher.last_diagnostic.update(
            result_age_ms=round(age * 1000),
            queue_wait_ms=round(max(0, job.claimed_at - job.created) * 1000),
            observed_passage=observed,
            confirmed_passages=sorted(session.confirmed_passages),
            passage_count=len(session.matcher.sentences),
        )
        if payload.debug:
            base = db.get(Sermon, session.base_id)
            return {
                "status": "accepted",
                "debug": dict(
                    session.matcher.last_diagnostic,
                    state=session.matcher.state,
                    highlight_word_index=session.matcher.position,
                    sermon_id=session.base_id,
                    highlight_count=len(live.public_state(base, base.id)["highlights"]) if base else 0,
                ),
            }
    return {"status": "accepted"}


@router.post("/live-worker/offline", status_code=204)
async def worker_offline(worker: LiveWorkerToken = Depends(get_worker)):
    live.WORKERS.pop(worker.id, None)
