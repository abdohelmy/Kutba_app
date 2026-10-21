"""Single-worker, bounded live session buffers. Audio never goes into the database."""

import asyncio
import hashlib
import io
import json
import secrets
import time
import wave
from dataclasses import dataclass, field

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Sermon, SermonStatus
from app.services.danish import english_is_current
from app.services.live_matcher import LiveMatcher
from app.services.sentence_alignment import align_sentences

MAX_AUDIO_BYTES = 400_000
MAX_SESSIONS = 4
SESSION_SECONDS = 3 * 60 * 60
LOCK = asyncio.Lock()
PREPARING: set[str] = set()
ERRORS: dict[str, str] = {}
WORKERS: dict[str, float] = {}
_preparation_limit = asyncio.Semaphore(2)


def segment_revision(segment) -> str:
    return hashlib.sha256(
        json.dumps([segment.arabic_text, segment.translated_text], ensure_ascii=False).encode()
    ).hexdigest()


def sermon_revision(sermon) -> str:
    return hashlib.sha256(
        "".join(segment_revision(s) for s in sermon.segments).encode()
    ).hexdigest()


def mapping_ready(sermon) -> bool:
    return bool(
        sermon.segments
        and all(
            s.live_alignment
            and s.live_alignment.get("revision") == segment_revision(s)
            and s.live_alignment.get("links")
            for s in sermon.segments
        )
    )


def worker_ready() -> bool:
    now = time.monotonic()
    for identity in list(WORKERS):
        if now - WORKERS[identity] > 30:
            del WORKERS[identity]
    return bool(WORKERS)


def validate_wav(audio: bytes) -> None:
    if len(audio) > MAX_AUDIO_BYTES:
        raise ValueError("Audio chunk is too large")
    try:
        with wave.open(io.BytesIO(audio)) as wav:
            if (
                wav.getnchannels() != 1
                or wav.getsampwidth() != 2
                or wav.getframerate() != 16000
                or wav.getcomptype() != "NONE"
                or not 8000 <= wav.getnframes() <= 160000
            ):
                raise ValueError("Use mono 16 kHz PCM16 WAV chunks of 0.5–10 seconds")
            if len(wav.readframes(wav.getnframes())) != wav.getnframes() * 2:
                raise ValueError("Incomplete audio chunk")
    except (wave.Error, EOFError) as exc:
        raise ValueError("Invalid WAV audio") from exc


@dataclass
class AudioJob:
    sequence: int
    audio: bytes
    kind: str = "full"
    created: float = field(default_factory=time.monotonic)
    identity: str = field(default_factory=lambda: secrets.token_urlsafe(16))
    claimed_by: str | None = None
    claimed_at: float = 0


@dataclass
class LiveSession:
    base_id: str
    mosque_id: str
    revision: str
    matcher: LiveMatcher
    identity: str = field(default_factory=lambda: secrets.token_urlsafe(16))
    started: float = field(default_factory=time.monotonic)
    touched: float = field(default_factory=time.monotonic)
    audio_received: float = 0
    paused: bool = False
    sequence: int = -1
    epoch: int = 0
    jobs: list[AudioJob] = field(default_factory=list)
    confirmed_passages: dict[int, dict] = field(default_factory=dict)
    preview_anchor: tuple[int, float] | None = None
    reading_words_per_second: float = 2.0
    preview_passage: int | None = None
    preview_basis: str | None = None


SESSIONS: dict[str, LiveSession] = {}


def clean_sessions() -> None:
    now = time.monotonic()
    for identity, session in list(SESSIONS.items()):
        if now - session.started > SESSION_SECONDS or now - session.touched > 90:
            session.jobs.clear()
            del SESSIONS[identity]
        else:
            session.jobs[:] = [j for j in session.jobs if now - j.created < 25]


def session_for(base_id: str) -> LiveSession | None:
    clean_sessions()
    return SESSIONS.get(base_id)


def reset_session_buffers(session: LiveSession) -> None:
    session.epoch += 1
    session.jobs.clear()
    session.matcher.history.clear()
    session.matcher.pending = None
    session.matcher.local_pending = None
    session.matcher.audio_end = None
    session.matcher.state = "waiting"
    session.preview_anchor = None


def record_passage(session: LiveSession, sequence: int) -> int | None:
    """Record observed locations only. Skipped passages are never marked read."""
    position = session.matcher.position
    if position is None:
        return None
    passage = next((i for i, (a, b, _) in enumerate(session.matcher.sentences)
                    if a <= position < b), None)
    if passage is not None:
        audio_time = session.matcher.audio_end
        if audio_time is not None:
            previous = session.preview_anchor
            if previous and position > previous[0]:
                delta, elapsed = position - previous[0], audio_time - previous[1]
                # Learn pace only from small, fresh moves, not re-acquisition
                # jumps or a long digression. Smooth changes to avoid flicker.
                if 2 <= elapsed <= 16 and delta <= 30:
                    pace = max(1.0, min(3.5, delta / elapsed))
                    session.reading_words_per_second = .8 * session.reading_words_per_second + .2 * pace
            if previous is None or position > previous[0]:
                session.preview_anchor = (position, audio_time)
        record = session.confirmed_passages.setdefault(passage, {"first_sequence": sequence})
        record["last_sequence"] = sequence
    return passage


def public_state(sermon, base_id: str) -> dict:
    session = session_for(base_id)
    result = {
        "active": bool(session),
        "status": "idle",
        "highlights": [],
        "tentative_highlights": [],
        "session_id": session.identity if session else None,
        "sequence": -1,
        "provisional": False,
    }
    if session is None:
        return result
    result["sequence"] = session.matcher.last_sequence
    if not mapping_ready(sermon):
        result["status"] = "mapping_required"
        return result
    if session.paused:
        result["status"] = "paused"
    elif not worker_ready():
        result["status"] = "worker_offline"
    elif time.monotonic() - session.audio_received > 15:
        result["status"] = "waiting_for_audio"
    else:
        result["status"] = session.matcher.state
    current = session.matcher.current
    if current is None and session.matcher.script:
        # A display default must never become evidence for the matcher. A new
        # session can still acquire its first real position anywhere in the text.
        current = session.matcher.script[0]
        result["provisional"] = True
    def mapped_highlights(current):
        if not current:
            return []
        original = next(
            (
                s
                for s in sermon.segments
                if s.ordinal == current_ordinal(session, current.segment_id)
            ),
            None,
        )
        if original:
            links = original.live_alignment.get("links", [])
            covering = [
                link for link in links if link["arabic_start"] <= current.start < link["arabic_end"]
            ]
            # Unknown alignment stays unhighlighted, never inferred proportionally.
            if covering:
                shortest = min(link["arabic_end"] - link["arabic_start"] for link in covering)
                return [
                    dict(
                        segment_id=original.id,
                        start=link["translation_start"],
                        end=link["translation_end"],
                        excerpt=(original.translated_text or "")
                        .encode("utf-16-le")[
                            link["translation_start"] * 2 : link["translation_end"] * 2
                        ]
                        .decode("utf-16-le"),
                    )
                    for link in covering
                    if link["arabic_end"] - link["arabic_start"] == shortest
                ]
        return []
    result["highlights"] = mapped_highlights(current)
    if current and not result["provisional"]:
        current_passage = next((i for i, (a, b, _) in enumerate(session.matcher.sentences)
                                if a <= session.matcher.position < b), None)
        if current_passage is not None and current_passage + 1 < len(session.matcher.sentences):
            start, end, _ = session.matcher.sentences[current_passage]
            heard = session.matcher.position - start + 1
            remaining = end - session.matcher.position - 1
            word_trigger = heard * 4 >= (end - start) * 3 and remaining <= 3
            estimated_heard = heard
            timer_trigger = False
            anchor = session.preview_anchor
            if (anchor and anchor[0] == session.matcher.position
                    and result["status"] in {"matched", "waiting"}
                    and time.monotonic() - session.audio_received <= 4):
                # Audio receipt time includes processing/queue delay in the
                # estimate. Limit extrapolation when matching has stalled.
                elapsed = max(0, min(12, time.monotonic() - anchor[1]))
                estimated_heard += elapsed * session.reading_words_per_second
                timer_trigger = estimated_heard >= end - start
            # Latch the display cue until green reaches/passes this passage.
            # Neither the estimate nor the latch affects authoritative matching.
            if word_trigger or timer_trigger:
                if session.preview_passage != current_passage + 1:
                    session.preview_basis = "timer"
                session.preview_passage = current_passage + 1
                if word_trigger:
                    session.preview_basis = "words"
            if session.preview_passage == current_passage + 1:
                next_start = session.matcher.sentences[current_passage + 1][0]
                tentative = mapped_highlights(session.matcher.script[next_start])
                result["tentative_highlights"] = [
                    dict(h, basis=session.preview_basis) for h in tentative
                    if h not in result["highlights"]
                ]
            elif session.preview_passage is not None:
                session.preview_passage = None
                session.preview_basis = None
        else:
            session.preview_passage = None
            session.preview_basis = None
    return result


def current_ordinal(session: LiveSession, segment_id: str) -> int:
    # Segment ids differ in Danish; the shared Arabic source is identified by ordinal.
    return int(segment_id)


def queue_preparation(background, base_id: str) -> None:
    """Called on the API event loop after publication, or for legacy recovery."""
    if base_id not in PREPARING:
        PREPARING.add(base_id)
        ERRORS.pop(base_id, None)
        background.add_task(prepare_mapping, base_id)


async def prepare_mapping(base_id: str) -> None:
    async with _preparation_limit:
        await _prepare_mapping(base_id)


async def _prepare_mapping(base_id: str) -> None:
    try:
        with SessionLocal() as db:
            base = db.get(Sermon, base_id)
            if not base or base.status != SermonStatus.PUBLISHED:
                raise ValueError("Publish the English khutba first")
            variants = [
                base,
                *db.scalars(
                    select(Sermon).where(
                        Sermon.english_sermon_id == base_id, Sermon.status == SermonStatus.PUBLISHED
                    )
                ),
            ]
            for sermon in variants:
                if not english_is_current(sermon, db):
                    continue
                for segment in sermon.segments:
                    revision = segment_revision(segment)
                    if segment.live_alignment.get(
                        "revision"
                    ) == revision and segment.live_alignment.get("links"):
                        continue
                    english = (
                        next(
                            (
                                s.translated_text
                                for s in base.segments
                                if s.ordinal == segment.ordinal
                            ),
                            None,
                        )
                        if sermon.english_sermon_id
                        else None
                    )
                    links = await align_sentences(
                        segment.arabic_text, segment.translated_text or "", english
                    )
                    if not links:
                        raise ValueError(
                            "No reliable sentence mappings found. Review the translation first."
                        )
                    db.refresh(segment)
                    if segment_revision(segment) != revision:
                        raise ValueError("The khutba changed while preparing. Retry live highlighting.")
                    segment.live_alignment = {
                        "revision": revision,
                        "links": [link.model_dump() for link in links],
                    }
                    db.commit()
        ERRORS.pop(base_id, None)
    except Exception as exc:
        ERRORS[base_id] = (
            str(exc)
            if isinstance(exc, ValueError)
            else "Live preparation failed. Try again; the published khutba is unchanged."
        )
    finally:
        PREPARING.discard(base_id)
