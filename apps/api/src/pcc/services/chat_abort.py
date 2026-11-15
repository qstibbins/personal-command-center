"""In-process abort registry for in-flight chat runs (Phase 1A.2 PR3).

Cancel route and streaming generator share a ``threading.Event`` per run id.

**Single-worker assumption:** handles are process-local. Cross-worker cancel
cannot signal another process's generator. Abandoned DB ``running`` rows
(no local handle) are recovered by ``chat_recovery`` when
``pcc_chat_assume_single_worker`` is true. Do not scale ``pcc-api`` above one
instance until a shared abort/lease mechanism exists.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass


@dataclass
class AbortHandle:
    event: threading.Event
    cancel_reason: str | None = None


_lock = threading.Lock()
_handles: dict[uuid.UUID, AbortHandle] = {}


def register_run(run_id: uuid.UUID) -> AbortHandle:
    handle = AbortHandle(event=threading.Event())
    with _lock:
        _handles[run_id] = handle
    return handle


def get_handle(run_id: uuid.UUID) -> AbortHandle | None:
    with _lock:
        return _handles.get(run_id)


def request_cancel(run_id: uuid.UUID, *, reason: str) -> AbortHandle | None:
    with _lock:
        handle = _handles.get(run_id)
        if handle is None:
            return None
        if handle.cancel_reason is None:
            handle.cancel_reason = reason
        handle.event.set()
        return handle


def unregister_run(run_id: uuid.UUID) -> None:
    with _lock:
        _handles.pop(run_id, None)


def clear_all_for_tests() -> None:
    with _lock:
        _handles.clear()
