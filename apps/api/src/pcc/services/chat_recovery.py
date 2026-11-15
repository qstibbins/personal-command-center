"""Abandoned running-run recovery (Phase 1A.2 PR3 follow-up).

Strategy (single-process MVP):
- Live claims register an in-process abort handle **before** committing the
  ``running`` row, so same-process recovery never observes a committed live
  run without a handle.
- A DB row with ``status='running'`` and **no** local handle is abandoned
  (process crash / restart). Finalizing it is only safe when exactly one
  ``pcc-api`` process is active.
- Legitimately active streams are never recovered: presence of a local handle
  means the stream is alive in this process (no wall-clock timeout).

``pcc_chat_assume_single_worker`` only gates whether this recovery runs; it
does not enforce topology. Overlapping API processes (scale-out or rolling
deploy overlap) can incorrectly finalize live peer runs. Multi-worker
cancel/recovery remains unsupported.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from pcc.core.config import get_settings
from pcc.db import session as db_session
from pcc.db.models import ChatRun, Message
from pcc.services.chat_abort import get_handle

logger = logging.getLogger(__name__)

# cancel_reason already allowed by ck_chat_runs_cancel_reason; unused in 1A streams.
RECOVERY_CANCEL_REASON = "superseded"
RECOVERY_ERROR_CODE = "cancelled"
RECOVERY_ERROR_MESSAGE = "Abandoned run recovered after process restart"


class ActiveRunError(Exception):
    """Conversation has a live (locally active) running run."""


def assumes_single_worker() -> bool:
    return bool(get_settings().pcc_chat_assume_single_worker)


def is_locally_active(run_id: uuid.UUID) -> bool:
    return get_handle(run_id) is not None


def finalize_abandoned_run(
    db: Session,
    run: ChatRun,
    *,
    cancel_reason: str = RECOVERY_CANCEL_REASON,
    error_message: str = RECOVERY_ERROR_MESSAGE,
) -> bool:
    """Mark an abandoned running run + streaming assistant terminal.

    Returns True if this session transitioned the run out of ``running``.
    Caller must hold appropriate locks / be the only writer for this run.
    Does nothing if the run is no longer ``running`` or is locally active.
    """
    if run.status != "running":
        return False
    if is_locally_active(run.id):
        return False

    now = datetime.now(UTC)
    run.status = "cancelled"
    run.finished_at = now
    run.cancel_reason = cancel_reason
    run.error_code = RECOVERY_ERROR_CODE
    run.error_message = error_message

    if run.response_message_id is not None:
        assistant = db.get(Message, run.response_message_id)
        if assistant is not None and assistant.status == "streaming":
            # In-flight buffer was process-local and is lost (architecture §K).
            assistant.status = "partial"
            assistant.completed_at = now
            assistant.updated_at = now
            assistant.error_code = RECOVERY_ERROR_CODE
            assistant.error_message = error_message

    db.flush()
    logger.warning(
        "Recovered abandoned chat run id=%s conversation_id=%s reason=%s",
        run.id,
        run.conversation_id,
        cancel_reason,
    )
    return True


def recover_abandoned_runs_locked(
    db: Session,
    *,
    conversation_id: uuid.UUID | None = None,
) -> list[uuid.UUID]:
    """Finalize abandoned ``running`` rows visible in this session.

    When ``conversation_id`` is set, only that conversation is considered
    (caller should hold ``FOR UPDATE`` on the conversation row).
    """
    if not assumes_single_worker():
        return []

    statement = select(ChatRun).where(ChatRun.status == "running")
    if conversation_id is not None:
        statement = statement.where(ChatRun.conversation_id == conversation_id)

    recovered: list[uuid.UUID] = []
    for run in db.scalars(statement).all():
        if finalize_abandoned_run(db, run):
            recovered.append(run.id)
    return recovered


def recover_all_abandoned_running_runs(
    *,
    session_factory=None,
) -> list[uuid.UUID]:
    """Startup / admin path: recover every abandoned running run in the DB."""
    if not assumes_single_worker():
        logger.warning(
            "Skipping abandoned chat-run recovery because "
            "pcc_chat_assume_single_worker is false"
        )
        return []

    factory = session_factory or db_session.SessionLocal
    with factory() as db:
        recovered = recover_abandoned_runs_locked(db)
        db.commit()
        return recovered
