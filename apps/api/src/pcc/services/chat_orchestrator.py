"""Chat claim / stream / finalize orchestrator (Phase 1A.2 PR3).

Short DB transactions only — never hold a session open across provider.stream().
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pcc.db import session as db_session
from pcc.db.models import ChatRun, Conversation, Message, MessageUsage
from pcc.providers.base import ChatMessageDTO, StreamEvent, UsageInfo
from pcc.providers.registry import get_provider
from pcc.services.chat_abort import register_run, request_cancel, unregister_run
from pcc.services.chat_conversations import ChatNotFoundError, get_conversation
from pcc.services.chat_ownership import normalize_owner_email
from pcc.services.chat_recovery import (
    finalize_abandoned_run,
    is_locally_active,
    recover_abandoned_runs_locked,
)

logger = logging.getLogger(__name__)

TITLE_MAX = 300
RUNNING_UNIQUE_INDEX = "uq_chat_runs_one_running_per_conversation"

# Test-only synchronization hooks (must stay None in production).
_claim_after_register_before_commit: Callable[[uuid.UUID], None] | None = None
_claim_after_commit: Callable[[uuid.UUID], None] | None = None


def _session_factory():
    """Resolve SessionLocal at call time so tests can rebind the factory."""
    return db_session.SessionLocal


class RunInProgressError(Exception):
    """Raised when a conversation already has a running chat run."""


@dataclass(frozen=True)
class ClaimResult:
    conversation_id: uuid.UUID
    owner_email: str
    run_id: uuid.UUID
    request_message_id: uuid.UUID
    response_message_id: uuid.UUID
    provider: str
    model: str
    context: list[ChatMessageDTO]


@dataclass
class StreamOutcome:
    content: str
    usage: UsageInfo | None
    message_status: str  # complete | partial | failed
    run_status: str  # completed | cancelled | failed
    cancel_reason: str | None
    error_code: str | None
    error_message: str | None
    finish_reason: str | None


def claim_turn(
    *,
    conversation_id: uuid.UUID,
    owner_email: str,
    content: str,
    session_factory=None,
) -> ClaimResult:
    """Lock conversation, allocate sequences, insert user + assistant + running run.

    The local abort handle is registered **before** ``commit`` so concurrent
    recovery cannot observe a committed ``running`` row without a live handle.
    Failed flush/commit always unregisters and rolls back.
    """
    session_factory = session_factory or _session_factory()
    owner = normalize_owner_email(owner_email)
    registered_run_id: uuid.UUID | None = None
    with session_factory() as db:
        try:
            conversation = (
                db.execute(
                    select(Conversation)
                    .where(
                        Conversation.id == conversation_id,
                        Conversation.owner_email == owner,
                        Conversation.status != "deleted",
                    )
                    .with_for_update()
                )
                .scalar_one_or_none()
            )
            if conversation is None:
                raise ChatNotFoundError("Conversation not found")

            # Crash leftovers: running + no local handle → recover, then claim.
            recover_abandoned_runs_locked(db, conversation_id=conversation_id)

            existing = db.scalar(
                select(ChatRun.id).where(
                    ChatRun.conversation_id == conversation_id,
                    ChatRun.status == "running",
                )
            )
            if existing is not None:
                raise RunInProgressError("A reply is already in progress")

            user_seq = _allocate_sequence(db, conversation_id)
            assistant_seq = _allocate_sequence(db, conversation_id)

            user_message = Message(
                id=uuid.uuid4(),
                conversation_id=conversation_id,
                owner_email=owner,
                role="user",
                status="complete",
                content_text=content,
                sequence=user_seq,
                completed_at=datetime.now(UTC),
            )
            assistant_message = Message(
                id=uuid.uuid4(),
                conversation_id=conversation_id,
                owner_email=owner,
                role="assistant",
                status="streaming",
                content_text="",
                provider=conversation.default_provider,
                model=conversation.default_model,
                sequence=assistant_seq,
            )
            run = ChatRun(
                id=uuid.uuid4(),
                conversation_id=conversation_id,
                owner_email=owner,
                status="running",
                provider=conversation.default_provider,
                model=conversation.default_model,
                request_message_id=user_message.id,
                response_message_id=assistant_message.id,
            )
            db.add_all([user_message, assistant_message, run])

            if conversation.title is None:
                conversation.title = _title_from_user_content(content)
            conversation.updated_at = datetime.now(UTC)

            context = _load_context(db, conversation)
            # Append the just-created user message (already in session).
            context.append(ChatMessageDTO(role="user", content=content))

            # Register before commit: once the running row is visible to other
            # sessions, recovery must already see a local abort handle.
            register_run(run.id)
            registered_run_id = run.id
            if _claim_after_register_before_commit is not None:
                _claim_after_register_before_commit(run.id)

            db.commit()
        except IntegrityError as exc:
            db.rollback()
            if registered_run_id is not None:
                unregister_run(registered_run_id)
                registered_run_id = None
            if _is_running_unique_violation(exc):
                raise RunInProgressError("A reply is already in progress") from exc
            logger.exception("Unexpected integrity error during chat claim")
            raise
        except Exception:
            db.rollback()
            if registered_run_id is not None:
                unregister_run(registered_run_id)
                registered_run_id = None
            raise

        if _claim_after_commit is not None:
            _claim_after_commit(run.id)

        return ClaimResult(
            conversation_id=conversation_id,
            owner_email=owner,
            run_id=run.id,
            request_message_id=user_message.id,
            response_message_id=assistant_message.id,
            provider=conversation.default_provider,
            model=conversation.default_model,
            context=context,
        )


def iter_sse_for_claim(claim: ClaimResult) -> Iterator[str]:
    """Stream SSE events for a claimed turn; finalize in a short session afterward."""
    from pcc.services.chat_abort import get_handle

    handle = get_handle(claim.run_id)
    abort = handle.event if handle is not None else __import__("threading").Event()
    provider = get_provider(claim.provider)

    buffer: list[str] = []
    usage: UsageInfo | None = None
    outcome: StreamOutcome | None = None
    client_gone = False

    def _sse(event_name: str, payload: dict) -> str:
        return f"event: {event_name}\ndata: {json.dumps(payload, default=str)}\n\n"

    try:
        yield _sse(
            "message_start",
            {
                "run_id": str(claim.run_id),
                "message_id": str(claim.response_message_id),
                "role": "assistant",
            },
        )

        for event in provider.stream(
            model=claim.model,
            messages=claim.context,
            tools=None,
            temperature=None,
            max_output_tokens=None,
            abort=abort,
        ):
            mapped = _map_provider_event(event, claim)
            if mapped is None:
                continue
            event_name, payload, partial_outcome = mapped
            if "delta" in payload and event_name == "content_delta":
                buffer.append(str(payload["delta"]))
            if event.get("type") == "usage":
                usage = event.get("usage")
            if partial_outcome is not None:
                outcome = partial_outcome
                outcome.content = "".join(buffer)
                if usage is not None:
                    outcome.usage = usage
            yield _sse(event_name, payload)
            if event_name in {"message_end", "error"}:
                break

        if outcome is None:
            # Clean stream end without explicit terminal from mapper.
            cancel_reason = handle.cancel_reason if handle else None
            if abort.is_set():
                outcome = StreamOutcome(
                    content="".join(buffer),
                    usage=usage,
                    message_status="partial",
                    run_status="cancelled",
                    cancel_reason=cancel_reason or "disconnect",
                    error_code="cancelled",
                    error_message="Stopped",
                    finish_reason="cancelled",
                )
            else:
                outcome = StreamOutcome(
                    content="".join(buffer),
                    usage=usage,
                    message_status="complete",
                    run_status="completed",
                    cancel_reason=None,
                    error_code=None,
                    error_message=None,
                    finish_reason="stop",
                )
    except GeneratorExit:
        client_gone = True
        abort.set()
        if handle is not None and handle.cancel_reason is None:
            handle.cancel_reason = "disconnect"
        outcome = StreamOutcome(
            content="".join(buffer),
            usage=usage,
            message_status="partial",
            run_status="cancelled",
            cancel_reason="disconnect",
            error_code="cancelled",
            error_message="Client disconnected",
            finish_reason="cancelled",
        )
        raise
    except Exception:
        logger.exception("chat stream failed run_id=%s", claim.run_id)
        outcome = StreamOutcome(
            content="".join(buffer),
            usage=usage,
            message_status="failed",
            run_status="failed",
            cancel_reason=None,
            error_code="internal",
            error_message="Internal stream error",
            finish_reason="error",
        )
        if not client_gone:
            yield _sse(
                "error",
                {
                    "message_id": str(claim.response_message_id),
                    "code": "internal",
                    "message": "Internal stream error",
                    "partial": bool(buffer),
                },
            )
    finally:
        if outcome is None:
            outcome = StreamOutcome(
                content="".join(buffer),
                usage=usage,
                message_status="partial",
                run_status="cancelled",
                cancel_reason="disconnect",
                error_code="cancelled",
                error_message="Interrupted",
                finish_reason="cancelled",
            )
        # Prefer explicit cancel reason from abort registry when present.
        if handle is not None and handle.cancel_reason and outcome.run_status == "cancelled":
            outcome.cancel_reason = handle.cancel_reason

        finalize_turn(claim=claim, outcome=outcome)
        unregister_run(claim.run_id)


def finalize_turn(
    *,
    claim: ClaimResult,
    outcome: StreamOutcome,
    session_factory=None,
) -> None:
    session_factory = session_factory or _session_factory()
    """Persist assistant terminal state + usage + run status (idempotent-ish)."""
    now = datetime.now(UTC)
    with session_factory() as db:
        assistant = db.get(Message, claim.response_message_id)
        run = db.get(ChatRun, claim.run_id)
        conversation = db.get(Conversation, claim.conversation_id)
        if assistant is None or run is None:
            logger.error(
                "finalize missing rows run_id=%s message_id=%s",
                claim.run_id,
                claim.response_message_id,
            )
            return

        # Idempotent: if run already terminal, leave it.
        if run.status != "running":
            db.commit()
            return

        assistant.content_text = outcome.content
        assistant.status = outcome.message_status
        assistant.error_code = outcome.error_code
        assistant.error_message = outcome.error_message
        assistant.completed_at = now
        assistant.updated_at = now
        assistant.provider = claim.provider
        assistant.model = claim.model

        if outcome.usage is not None:
            usage_row = db.get(MessageUsage, assistant.id)
            if usage_row is None:
                usage_row = MessageUsage(message_id=assistant.id)
                db.add(usage_row)
            usage_row.input_tokens = outcome.usage.get("input_tokens")
            usage_row.output_tokens = outcome.usage.get("output_tokens")
            usage_row.total_tokens = outcome.usage.get("total_tokens")
            usage_row.cost_micros = outcome.usage.get("cost_micros")
            usage_row.raw = dict(outcome.usage)

        run.status = outcome.run_status
        run.finished_at = now
        run.error_code = outcome.error_code
        run.error_message = outcome.error_message
        run.cancel_reason = outcome.cancel_reason

        if conversation is not None:
            conversation.updated_at = now

        db.commit()


def cancel_run(
    *,
    run_id: uuid.UUID,
    owner_email: str,
    session_factory=None,
) -> ChatRun:
    """Request cancel for an in-flight run; idempotent if already terminal.

    If the run is ``running`` but has no local abort handle (abandoned after
    crash), finalize it immediately under the single-worker assumption.
    Abandoned recovery takes the conversation ``FOR UPDATE`` so it cannot race
    a concurrent claim that still holds the conversation lock.
    """
    session_factory = session_factory or _session_factory()
    owner = normalize_owner_email(owner_email)
    with session_factory() as db:
        run = db.get(ChatRun, run_id)
        if run is None or run.owner_email != owner:
            raise ChatNotFoundError("Run not found")

        if run.status != "running":
            return run

        if is_locally_active(run_id):
            request_cancel(run_id, reason="client_stop")
            db.refresh(run)
            return run

        # Serialize with claim/delete on the same conversation.
        db.execute(
            select(Conversation)
            .where(Conversation.id == run.conversation_id)
            .with_for_update()
        )
        db.refresh(run)
        if run.status != "running":
            return run
        if is_locally_active(run_id):
            request_cancel(run_id, reason="client_stop")
            db.refresh(run)
            return run

        # No local generator: recover abandoned row so cancel is effective.
        finalize_abandoned_run(
            db,
            run,
            cancel_reason="client_stop",
            error_message="Cancelled after abandoned run recovery",
        )
        db.commit()
        db.refresh(run)
        return run


def _is_running_unique_violation(exc: IntegrityError) -> bool:
    message = str(getattr(exc, "orig", exc)).lower()
    return RUNNING_UNIQUE_INDEX.lower() in message or (
        "chat_runs" in message and "running" in message
    )


def _allocate_sequence(db: Session, conversation_id: uuid.UUID) -> int:
    row = db.execute(
        text(
            "UPDATE conversations "
            "SET next_sequence = next_sequence + 1, updated_at = CURRENT_TIMESTAMP "
            "WHERE id = :id "
            "RETURNING next_sequence - 1"
        ),
        {"id": conversation_id},
    ).scalar_one()
    return int(row)


def _load_context(db: Session, conversation: Conversation) -> list[ChatMessageDTO]:
    messages: list[ChatMessageDTO] = []
    if conversation.system_prompt:
        messages.append(
            ChatMessageDTO(role="system", content=conversation.system_prompt)
        )
    rows = db.scalars(
        select(Message)
        .where(
            Message.conversation_id == conversation.id,
            Message.status.in_(("complete", "partial")),
        )
        .order_by(Message.sequence.asc())
    ).all()
    for row in rows:
        if row.role in {"system", "user", "assistant", "tool"}:
            messages.append(ChatMessageDTO(role=row.role, content=row.content_text))
    return messages


def _title_from_user_content(content: str) -> str:
    collapsed = " ".join(content.split())
    if len(collapsed) <= TITLE_MAX:
        return collapsed
    return collapsed[: TITLE_MAX - 1].rstrip() + "…"


def _map_provider_event(
    event: StreamEvent,
    claim: ClaimResult,
) -> tuple[str, dict, StreamOutcome | None] | None:
    message_id = str(claim.response_message_id)
    event_type = event["type"]

    if event_type == "message_start":
        # Already emitted with run_id by orchestrator.
        return None

    if event_type == "content_delta":
        return (
            "content_delta",
            {"message_id": message_id, "delta": event.get("delta") or ""},
            None,
        )

    if event_type == "usage":
        usage = event.get("usage") or {}
        return (
            "usage",
            {
                "message_id": message_id,
                "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "cost_micros": usage.get("cost_micros"),
            },
            None,
        )

    if event_type == "message_end":
        status = event.get("status") or "complete"
        finish = event.get("finish_reason") or "stop"
        outcome = StreamOutcome(
            content="",
            usage=None,
            message_status="complete" if status == "complete" else status,
            run_status="completed",
            cancel_reason=None,
            error_code=None,
            error_message=None,
            finish_reason=finish,
        )
        return (
            "message_end",
            {
                "message_id": message_id,
                "status": outcome.message_status,
                "finish_reason": finish,
            },
            outcome,
        )

    if event_type == "error":
        code = event.get("error_code") or "internal"
        message = event.get("message") or "Provider error"
        if code == "cancelled":
            from pcc.services.chat_abort import get_handle

            handle = get_handle(claim.run_id)
            cancel_reason = handle.cancel_reason if handle and handle.cancel_reason else "disconnect"
            outcome = StreamOutcome(
                content="",
                usage=None,
                message_status="partial",
                run_status="cancelled",
                cancel_reason=cancel_reason,
                error_code="cancelled",
                error_message=message,
                finish_reason="cancelled",
            )
        else:
            outcome = StreamOutcome(
                content="",
                usage=None,
                message_status="failed",
                run_status="failed",
                cancel_reason=None,
                error_code=code,
                error_message=message,
                finish_reason="error",
            )
        return (
            "error",
            {
                "message_id": message_id,
                "code": code,
                "message": message,
                "partial": True,
            },
            outcome,
        )

    return None


# Re-export get_conversation for cancel ownership checks in API layer.
__all__ = [
    "ClaimResult",
    "RunInProgressError",
    "StreamOutcome",
    "cancel_run",
    "claim_turn",
    "finalize_turn",
    "get_conversation",
    "iter_sse_for_claim",
]
