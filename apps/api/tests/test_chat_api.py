"""PostgreSQL-backed chat orchestration API tests (Phase 1A.2 PR3)."""

from __future__ import annotations

import json
import threading
import uuid
from unittest import mock

from auth_helpers import TEST_SERVICE_CREDENTIAL
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from pcc.auth.token_crypto import hash_api_token
from pcc.db import session as db_session
from pcc.db.models import ApiToken, ChatRun, Conversation, Message

OWNER = "owner@example.com"
OTHER = "other@example.com"


def _create_conversation(client, *, owner=OWNER, title=None):
    response = client.post(
        "/api/v1/chat/conversations",
        json={
            "owner_email": owner,
            "title": title,
            "default_provider": "mock",
            "default_model": "mock-echo-v1",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _parse_sse(body: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    event_name = None
    for line in body.splitlines():
        if line.startswith("event:"):
            event_name = line[len("event:") :].strip()
        elif line.startswith("data:") and event_name:
            events.append((event_name, json.loads(line[len("data:") :].strip())))
            event_name = None
    return events


def test_conversation_crud_and_ownership(db_client):
    created = _create_conversation(db_client, title="Hello")
    conv_id = created["id"]
    assert created["owner_email"] == OWNER
    assert created["status"] == "active"
    assert created["next_sequence"] == 1

    listed = db_client.get(
        "/api/v1/chat/conversations",
        params={"owner_email": OWNER},
    )
    assert listed.status_code == 200
    assert any(item["id"] == conv_id for item in listed.json())

    other_list = db_client.get(
        "/api/v1/chat/conversations",
        params={"owner_email": OTHER},
    )
    assert other_list.status_code == 200
    assert other_list.json() == []

    got = db_client.get(
        f"/api/v1/chat/conversations/{conv_id}",
        params={"owner_email": OWNER},
    )
    assert got.status_code == 200

    denied = db_client.get(
        f"/api/v1/chat/conversations/{conv_id}",
        params={"owner_email": OTHER},
    )
    assert denied.status_code == 404

    patched = db_client.patch(
        f"/api/v1/chat/conversations/{conv_id}",
        json={"owner_email": OWNER, "title": "Renamed", "status": "archived"},
    )
    assert patched.status_code == 200
    assert patched.json()["title"] == "Renamed"
    assert patched.json()["status"] == "archived"

    deleted = db_client.request(
        "DELETE",
        f"/api/v1/chat/conversations/{conv_id}",
        json={"owner_email": OWNER},
    )
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"

    missing = db_client.get(
        f"/api/v1/chat/conversations/{conv_id}",
        params={"owner_email": OWNER},
    )
    assert missing.status_code == 404


def test_message_stream_completed_and_ordering(db_client):
    conv = _create_conversation(db_client)
    conv_id = conv["id"]

    with db_client.stream(
        "POST",
        f"/api/v1/chat/conversations/{conv_id}/messages",
        json={"owner_email": OWNER, "content": "hello world"},
    ) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        body = "".join(response.iter_text())

    events = _parse_sse(body)
    names = [name for name, _ in events]
    assert names[0] == "message_start"
    assert "content_delta" in names
    assert "usage" in names
    assert names[-1] == "message_end"
    assert events[0][1]["run_id"]
    text = "".join(
        payload["delta"] for name, payload in events if name == "content_delta"
    )
    assert text.startswith("Echo: ")

    history = db_client.get(
        f"/api/v1/chat/conversations/{conv_id}/messages",
        params={"owner_email": OWNER},
    )
    assert history.status_code == 200
    messages = history.json()
    assert [m["sequence"] for m in messages] == [1, 2]
    assert messages[0]["role"] == "user"
    assert messages[0]["status"] == "complete"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["status"] == "complete"
    assert messages[1]["content_text"] == text

    # next_sequence advanced past both inserts
    refreshed = db_client.get(
        f"/api/v1/chat/conversations/{conv_id}",
        params={"owner_email": OWNER},
    ).json()
    assert refreshed["next_sequence"] == 3
    assert refreshed["title"] == "hello world"


def test_concurrent_run_returns_409(db_client):
    from pcc.services.chat_abort import register_run, unregister_run

    conv = _create_conversation(db_client)
    conv_id = uuid.UUID(conv["id"])
    run_id = uuid.uuid4()

    # Simulate a live in-process stream (local abort handle present).
    with db_session.SessionLocal() as session:
        session.add(
            ChatRun(
                id=run_id,
                conversation_id=conv_id,
                owner_email=OWNER,
                status="running",
                provider="mock",
                model="mock-echo-v1",
            )
        )
        session.commit()
    register_run(run_id)
    try:
        conflict = db_client.post(
            f"/api/v1/chat/conversations/{conv_id}/messages",
            json={"owner_email": OWNER, "content": "second"},
        )
        assert conflict.status_code == 409
        detail = conflict.json()["detail"]
        assert detail["code"] == "run_in_progress"
    finally:
        unregister_run(run_id)


def test_provider_error_persists_failed(db_client):
    conv = _create_conversation(db_client)
    conv_id = conv["id"]

    with db_client.stream(
        "POST",
        f"/api/v1/chat/conversations/{conv_id}/messages",
        json={"owner_email": OWNER, "content": "MOCK:ERROR:context_overflow"},
    ) as response:
        body = "".join(response.iter_text())

    events = _parse_sse(body)
    assert events[-1][0] == "error"
    assert events[-1][1]["code"] == "context_overflow"

    history = db_client.get(
        f"/api/v1/chat/conversations/{conv_id}/messages",
        params={"owner_email": OWNER},
    ).json()
    assistant = history[-1]
    assert assistant["role"] == "assistant"
    assert assistant["status"] == "failed"
    assert assistant["error_code"] == "context_overflow"

    with db_session.SessionLocal() as session:
        runs = session.scalars(select(ChatRun)).all()
        assert len(runs) == 1
        assert runs[0].status == "failed"
        # one-running constraint released
        assert session.scalar(
            select(ChatRun).where(ChatRun.status == "running")
        ) is None


def test_cancel_run_marks_partial(db_client):
    conv = _create_conversation(db_client)
    conv_id = conv["id"]

    # Use MOCK:SLOW with injected sleep that cancels mid-stream via API.
    cancel_called = {"done": False}

    def slow_sleep(_seconds: float) -> None:
        if cancel_called["done"]:
            return
        # Find running run and cancel it.
        with db_session.SessionLocal() as session:
            run = session.scalar(select(ChatRun).where(ChatRun.status == "running"))
            assert run is not None
            run_id = run.id
        cancel_called["done"] = True
        response = db_client.post(
            f"/api/v1/chat/runs/{run_id}/cancel",
            json={"owner_email": OWNER},
        )
        assert response.status_code == 200

    with (
        mock.patch("pcc.providers.mock.time.sleep", side_effect=slow_sleep),
        db_client.stream(
            "POST",
            f"/api/v1/chat/conversations/{conv_id}/messages",
            json={"owner_email": OWNER, "content": "MOCK:SLOW"},
        ) as response,
    ):
        body = "".join(response.iter_text())

    events = _parse_sse(body)
    assert any(name == "error" and payload.get("code") == "cancelled" for name, payload in events)

    history = db_client.get(
        f"/api/v1/chat/conversations/{conv_id}/messages",
        params={"owner_email": OWNER},
    ).json()
    assistant = history[-1]
    assert assistant["status"] == "partial"

    with db_session.SessionLocal() as session:
        run = session.scalar(select(ChatRun))
        assert run is not None
        assert run.status == "cancelled"
        assert run.cancel_reason == "client_stop"


def test_cancel_idempotent_when_terminal(db_client):
    conv = _create_conversation(db_client)
    conv_id = conv["id"]
    with db_client.stream(
        "POST",
        f"/api/v1/chat/conversations/{conv_id}/messages",
        json={"owner_email": OWNER, "content": "done"},
    ) as response:
        "".join(response.iter_text())

    with db_session.SessionLocal() as session:
        run = session.scalar(select(ChatRun))
        assert run is not None
        run_id = run.id
        assert run.status == "completed"

    again = db_client.post(
        f"/api/v1/chat/runs/{run_id}/cancel",
        json={"owner_email": OWNER},
    )
    assert again.status_code == 200
    assert again.json()["status"] == "completed"


def test_authorization_requires_service_credential(raw_db_client):
    missing = raw_db_client.get(
        "/api/v1/chat/conversations",
        params={"owner_email": OWNER},
    )
    assert missing.status_code == 401

    # Personal API token cannot call chat even with forged scopes in DB —
    # chat auth is service-principal only (no token verification path).
    with db_session.SessionLocal() as session:
        raw = "pcc_at_testtoken_chat_should_fail_xxxxxxxxxxxx"
        session.add(
            ApiToken(
                id=uuid.uuid4(),
                label="chat-deny",
                token_prefix="pcc_at_test",
                token_hash=hash_api_token(raw),
                scopes=["chat:read", "chat:write", "captures:read"],
                created_by_email=OWNER,
            )
        )
        session.commit()

    denied = raw_db_client.get(
        "/api/v1/chat/conversations",
        params={"owner_email": OWNER},
        headers={"Authorization": f"Bearer {raw}"},
    )
    assert denied.status_code == 401

    ok = raw_db_client.get(
        "/api/v1/chat/conversations",
        params={"owner_email": OWNER},
        headers={"Authorization": f"Bearer {TEST_SERVICE_CREDENTIAL}"},
    )
    assert ok.status_code == 200


def test_owner_email_required_and_normalized(db_client):
    bad = db_client.get("/api/v1/chat/conversations")
    assert bad.status_code == 422

    invalid = db_client.get(
        "/api/v1/chat/conversations",
        params={"owner_email": "not-an-email"},
    )
    assert invalid.status_code == 400

    created = db_client.post(
        "/api/v1/chat/conversations",
        json={"owner_email": "  Owner@Example.COM ", "default_provider": "mock", "default_model": "mock-echo-v1"},
    )
    assert created.status_code == 201
    assert created.json()["owner_email"] == "owner@example.com"


def test_isolation_between_owners(db_client):
    a = _create_conversation(db_client, owner=OWNER)
    b = _create_conversation(db_client, owner=OTHER)
    with db_client.stream(
        "POST",
        f"/api/v1/chat/conversations/{a['id']}/messages",
        json={"owner_email": OWNER, "content": "secret-a"},
    ) as response:
        "".join(response.iter_text())

    leaked = db_client.get(
        f"/api/v1/chat/conversations/{a['id']}/messages",
        params={"owner_email": OTHER},
    )
    assert leaked.status_code == 404

    other_history = db_client.get(
        f"/api/v1/chat/conversations/{b['id']}/messages",
        params={"owner_email": OTHER},
    )
    assert other_history.status_code == 200
    assert other_history.json() == []


def test_transactional_sequencing_across_turns(db_client):
    conv = _create_conversation(db_client)
    conv_id = conv["id"]
    for content in ("one", "two", "three"):
        with db_client.stream(
            "POST",
            f"/api/v1/chat/conversations/{conv_id}/messages",
            json={"owner_email": OWNER, "content": content},
        ) as response:
            "".join(response.iter_text())

    history = db_client.get(
        f"/api/v1/chat/conversations/{conv_id}/messages",
        params={"owner_email": OWNER},
    ).json()
    assert [m["sequence"] for m in history] == [1, 2, 3, 4, 5, 6]
    assert [m["role"] for m in history] == [
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
        "assistant",
    ]


def test_rate_limited_partial_content_failed(db_client):
    conv = _create_conversation(db_client)
    conv_id = conv["id"]
    with db_client.stream(
        "POST",
        f"/api/v1/chat/conversations/{conv_id}/messages",
        json={"owner_email": OWNER, "content": "MOCK:ERROR:rate_limited"},
    ) as response:
        body = "".join(response.iter_text())
    events = _parse_sse(body)
    assert any(name == "content_delta" for name, _ in events)
    assert events[-1][0] == "error"
    history = db_client.get(
        f"/api/v1/chat/conversations/{conv_id}/messages",
        params={"owner_email": OWNER},
    ).json()
    assert history[-1]["status"] == "failed"
    assert history[-1]["content_text"]  # partial buffer kept


def test_collect_stream_regression_imported():
    # Ensure provider regression stays in suite via import side (explicit).
    from pcc.providers.base import collect_stream

    result = collect_stream(
        iter(
            [
                {"type": "error", "error_code": "internal", "message": "boom"},
                {"type": "message_end", "finish_reason": "stop", "status": "complete"},
            ]
        )
    )
    assert result["finish_reason"] == "error"
    assert result["error_code"] == "internal"


def test_disconnect_finalize_releases_running_run(db_client):
    from pcc.services.chat_orchestrator import claim_turn, iter_sse_for_claim

    conv = _create_conversation(db_client)
    claim = claim_turn(
        conversation_id=uuid.UUID(conv["id"]),
        owner_email=OWNER,
        content="MOCK:SLOW hang on",
    )
    stream = iter_sse_for_claim(claim)
    assert "message_start" in next(stream)
    stream.close()  # simulate client disconnect / GeneratorExit

    with db_session.SessionLocal() as session:
        run = session.get(ChatRun, claim.run_id)
        assert run is not None
        assert run.status == "cancelled"
        assert run.cancel_reason == "disconnect"
        message = session.get(Message, claim.response_message_id)
        assert message is not None
        assert message.status == "partial"
        assert session.scalar(select(ChatRun).where(ChatRun.status == "running")) is None


def test_soft_delete_rejects_active_run(db_client):
    from pcc.services.chat_abort import register_run, unregister_run

    conv = _create_conversation(db_client)
    conv_id = uuid.UUID(conv["id"])
    run_id = uuid.uuid4()
    assistant_id = uuid.uuid4()

    with db_session.SessionLocal() as session:
        session.add(
            Message(
                id=assistant_id,
                conversation_id=conv_id,
                owner_email=OWNER,
                role="assistant",
                status="streaming",
                content_text="",
                sequence=1,
            )
        )
        session.add(
            ChatRun(
                id=run_id,
                conversation_id=conv_id,
                owner_email=OWNER,
                status="running",
                provider="mock",
                model="mock-echo-v1",
                response_message_id=assistant_id,
            )
        )
        session.commit()
    register_run(run_id)
    try:
        denied = db_client.request(
            "DELETE",
            f"/api/v1/chat/conversations/{conv_id}",
            json={"owner_email": OWNER},
        )
        assert denied.status_code == 409
        assert denied.json()["detail"]["code"] == "run_in_progress"
    finally:
        unregister_run(run_id)


def test_soft_delete_succeeds_after_completion(db_client):
    conv = _create_conversation(db_client)
    conv_id = conv["id"]
    with db_client.stream(
        "POST",
        f"/api/v1/chat/conversations/{conv_id}/messages",
        json={"owner_email": OWNER, "content": "done"},
    ) as response:
        "".join(response.iter_text())

    deleted = db_client.request(
        "DELETE",
        f"/api/v1/chat/conversations/{conv_id}",
        json={"owner_email": OWNER},
    )
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"


def test_soft_delete_recovers_abandoned_run_then_deletes(db_client):
    """Running without a local handle is abandoned → recover → delete allowed."""
    conv = _create_conversation(db_client)
    conv_id = uuid.UUID(conv["id"])
    run_id = uuid.uuid4()
    assistant_id = uuid.uuid4()

    with db_session.SessionLocal() as session:
        session.add(
            Message(
                id=assistant_id,
                conversation_id=conv_id,
                owner_email=OWNER,
                role="assistant",
                status="streaming",
                content_text="",
                sequence=1,
            )
        )
        session.add(
            ChatRun(
                id=run_id,
                conversation_id=conv_id,
                owner_email=OWNER,
                status="running",
                provider="mock",
                model="mock-echo-v1",
                response_message_id=assistant_id,
            )
        )
        session.commit()

    deleted = db_client.request(
        "DELETE",
        f"/api/v1/chat/conversations/{conv_id}",
        json={"owner_email": OWNER},
    )
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"

    with db_session.SessionLocal() as session:
        run = session.get(ChatRun, run_id)
        assert run is not None
        assert run.status == "cancelled"
        assert run.cancel_reason == "superseded"
        message = session.get(Message, assistant_id)
        assert message is not None
        assert message.status == "partial"


def test_claim_recovers_abandoned_run_then_streams(db_client):
    conv = _create_conversation(db_client)
    conv_id = uuid.UUID(conv["id"])
    stuck_run_id = uuid.uuid4()
    stuck_assistant = uuid.uuid4()

    with db_session.SessionLocal() as session:
        session.add(
            Message(
                id=stuck_assistant,
                conversation_id=conv_id,
                owner_email=OWNER,
                role="assistant",
                status="streaming",
                content_text="",
                sequence=1,
            )
        )
        session.add(
            ChatRun(
                id=stuck_run_id,
                conversation_id=conv_id,
                owner_email=OWNER,
                status="running",
                provider="mock",
                model="mock-echo-v1",
                response_message_id=stuck_assistant,
            )
        )
        # next_sequence must be past the stuck assistant sequence
        conversation = session.get(Conversation, conv_id)
        assert conversation is not None
        conversation.next_sequence = 2
        session.commit()

    with db_client.stream(
        "POST",
        f"/api/v1/chat/conversations/{conv_id}/messages",
        json={"owner_email": OWNER, "content": "after recovery"},
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())
    assert "message_end" in body or "content_delta" in body

    with db_session.SessionLocal() as session:
        stuck = session.get(ChatRun, stuck_run_id)
        assert stuck.status == "cancelled"
        assert stuck.cancel_reason == "superseded"
        assert session.scalar(select(ChatRun).where(ChatRun.status == "running")) is None


def test_recovery_does_not_steal_locally_active_run(db_client):
    from pcc.services.chat_abort import register_run, unregister_run
    from pcc.services.chat_recovery import recover_abandoned_runs_locked

    conv = _create_conversation(db_client)
    conv_id = uuid.UUID(conv["id"])
    run_id = uuid.uuid4()

    with db_session.SessionLocal() as session:
        session.add(
            ChatRun(
                id=run_id,
                conversation_id=conv_id,
                owner_email=OWNER,
                status="running",
                provider="mock",
                model="mock-echo-v1",
            )
        )
        session.commit()

    register_run(run_id)
    try:
        with db_session.SessionLocal() as session:
            session.execute(
                select(Conversation)
                .where(Conversation.id == conv_id)
                .with_for_update()
            )
            recovered = recover_abandoned_runs_locked(db=session, conversation_id=conv_id)
            session.commit()
            assert recovered == []
            run = session.get(ChatRun, run_id)
            assert run is not None
            assert run.status == "running"
    finally:
        unregister_run(run_id)


def test_startup_recovery_finalizes_abandoned_runs(db_client):
    from pcc.services.chat_recovery import recover_all_abandoned_running_runs

    conv = _create_conversation(db_client)
    conv_id = uuid.UUID(conv["id"])
    run_id = uuid.uuid4()
    assistant_id = uuid.uuid4()

    with db_session.SessionLocal() as session:
        session.add(
            Message(
                id=assistant_id,
                conversation_id=conv_id,
                owner_email=OWNER,
                role="assistant",
                status="streaming",
                content_text="",
                sequence=1,
            )
        )
        session.add(
            ChatRun(
                id=run_id,
                conversation_id=conv_id,
                owner_email=OWNER,
                status="running",
                provider="mock",
                model="mock-echo-v1",
                response_message_id=assistant_id,
            )
        )
        session.commit()

    recovered = recover_all_abandoned_running_runs()
    assert run_id in recovered

    with db_session.SessionLocal() as session:
        run = session.get(ChatRun, run_id)
        assert run.status == "cancelled"
        assert run.cancel_reason == "superseded"
        assert session.get(Message, assistant_id).status == "partial"
        # Conversation row still exists and is not deleted by recovery
        assert session.get(Conversation, conv_id).status == "active"


def test_concurrent_delete_while_send_returns_409(db_client):
    """While a locally active stream holds the running row, delete is 409."""
    from pcc.services.chat_orchestrator import claim_turn, iter_sse_for_claim

    conv = _create_conversation(db_client)
    claim = claim_turn(
        conversation_id=uuid.UUID(conv["id"]),
        owner_email=OWNER,
        content="MOCK:SLOW",
    )
    stream = iter_sse_for_claim(claim)
    next(stream)  # start stream; abort handle registered

    denied = db_client.request(
        "DELETE",
        f"/api/v1/chat/conversations/{conv['id']}",
        json={"owner_email": OWNER},
    )
    assert denied.status_code == 409
    assert denied.json()["detail"]["code"] == "run_in_progress"

    # Second send also blocked while first is active
    second = db_client.post(
        f"/api/v1/chat/conversations/{conv['id']}/messages",
        json={"owner_email": OWNER, "content": "nope"},
    )
    assert second.status_code == 409

    stream.close()
    # After disconnect finalize, delete succeeds
    deleted = db_client.request(
        "DELETE",
        f"/api/v1/chat/conversations/{conv['id']}",
        json={"owner_email": OWNER},
    )
    assert deleted.status_code == 200


def test_cross_owner_cancel_returns_404(db_client):
    conv = _create_conversation(db_client, owner=OWNER)
    with db_client.stream(
        "POST",
        f"/api/v1/chat/conversations/{conv['id']}/messages",
        json={"owner_email": OWNER, "content": "hi"},
    ) as response:
        "".join(response.iter_text())

    with db_session.SessionLocal() as session:
        run = session.scalar(select(ChatRun))
        assert run is not None
        run_id = run.id

    denied = db_client.post(
        f"/api/v1/chat/runs/{run_id}/cancel",
        json={"owner_email": OTHER},
    )
    assert denied.status_code == 404


def test_cancel_abandoned_run_finalizes(db_client):
    conv = _create_conversation(db_client)
    conv_id = uuid.UUID(conv["id"])
    run_id = uuid.uuid4()
    assistant_id = uuid.uuid4()

    with db_session.SessionLocal() as session:
        session.add(
            Message(
                id=assistant_id,
                conversation_id=conv_id,
                owner_email=OWNER,
                role="assistant",
                status="streaming",
                content_text="",
                sequence=1,
            )
        )
        session.add(
            ChatRun(
                id=run_id,
                conversation_id=conv_id,
                owner_email=OWNER,
                status="running",
                provider="mock",
                model="mock-echo-v1",
                response_message_id=assistant_id,
            )
        )
        session.commit()

    cancelled = db_client.post(
        f"/api/v1/chat/runs/{run_id}/cancel",
        json={"owner_email": OWNER},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["cancel_reason"] == "client_stop"


def test_recovery_cannot_steal_newly_claimed_run(db_client):
    """A. After commit, handle is already registered — recovery cannot steal."""
    from pcc.services import chat_orchestrator as orch
    from pcc.services.chat_abort import get_handle, unregister_run
    from pcc.services.chat_recovery import recover_abandoned_runs_locked

    conv = _create_conversation(db_client)
    conv_id = uuid.UUID(conv["id"])

    committed = threading.Event()
    recovery_done = threading.Event()
    observed: dict = {}

    def after_commit(run_id: uuid.UUID) -> None:
        # Invariant under register-before-commit: handle exists as soon as
        # the running row is committed/visible.
        assert get_handle(run_id) is not None
        observed["run_id"] = run_id
        committed.set()
        assert recovery_done.wait(timeout=5), "recovery thread timed out"

    def recovery_worker() -> None:
        assert committed.wait(timeout=5), "claim commit timed out"
        run_id = observed["run_id"]
        with db_session.SessionLocal() as session:
            recovered = recover_abandoned_runs_locked(
                session, conversation_id=conv_id
            )
            session.commit()
            run = session.get(ChatRun, run_id)
            observed["recovered"] = recovered
            observed["status"] = run.status if run is not None else None
        recovery_done.set()

    orch._claim_after_commit = after_commit
    try:
        thread = threading.Thread(target=recovery_worker, daemon=True)
        thread.start()
        claim = orch.claim_turn(
            conversation_id=conv_id,
            owner_email=OWNER,
            content="live claim",
        )
        thread.join(timeout=5)
        assert not thread.is_alive()
        assert observed["recovered"] == []
        assert observed["status"] == "running"
        assert claim.run_id == observed["run_id"]
        assert get_handle(claim.run_id) is not None
    finally:
        orch._claim_after_commit = None
        if "run_id" in observed:
            unregister_run(observed["run_id"])


def test_delete_cannot_succeed_while_newly_claimed_run_active(db_client):
    """B. Delete recovery sees the handle after commit and returns 409."""
    from pcc.services import chat_orchestrator as orch
    from pcc.services.chat_abort import get_handle, unregister_run
    from pcc.services.chat_conversations import soft_delete_conversation
    from pcc.services.chat_recovery import ActiveRunError

    conv = _create_conversation(db_client)
    conv_id = uuid.UUID(conv["id"])

    committed = threading.Event()
    delete_done = threading.Event()
    observed: dict = {}

    def after_commit(run_id: uuid.UUID) -> None:
        assert get_handle(run_id) is not None
        committed.set()
        assert delete_done.wait(timeout=5), "delete thread timed out"

    def delete_worker() -> None:
        assert committed.wait(timeout=5), "claim commit timed out"
        with db_session.SessionLocal() as session:
            try:
                soft_delete_conversation(
                    session, conversation_id=conv_id, owner_email=OWNER
                )
                observed["error"] = None
            except ActiveRunError as exc:
                observed["error"] = exc
                session.rollback()
        delete_done.set()

    orch._claim_after_commit = after_commit
    try:
        thread = threading.Thread(target=delete_worker, daemon=True)
        thread.start()
        claim = orch.claim_turn(
            conversation_id=conv_id,
            owner_email=OWNER,
            content="delete race",
        )
        observed["run_id"] = claim.run_id
        thread.join(timeout=5)
        assert not thread.is_alive()
        assert isinstance(observed.get("error"), ActiveRunError)

        with db_session.SessionLocal() as session:
            conversation = session.get(Conversation, conv_id)
            assert conversation is not None
            assert conversation.status == "active"
            run = session.get(ChatRun, claim.run_id)
            assert run is not None
            assert run.status == "running"
    finally:
        orch._claim_after_commit = None
        if "run_id" in observed:
            unregister_run(observed["run_id"])


def test_failed_claim_does_not_leave_orphaned_abort_handle(db_client):
    """C. Commit failure after register unregisters the handle."""
    from pcc.services import chat_orchestrator as orch
    from pcc.services.chat_abort import get_handle

    conv = _create_conversation(db_client)
    conv_id = uuid.UUID(conv["id"])
    seen_run_id: dict = {}

    def after_register(run_id: uuid.UUID) -> None:
        seen_run_id["id"] = run_id
        assert get_handle(run_id) is not None
        raise OperationalError("SELECT 1", {}, Exception("forced commit failure"))

    orch._claim_after_register_before_commit = after_register
    try:
        try:
            orch.claim_turn(
                conversation_id=conv_id,
                owner_email=OWNER,
                content="will fail",
            )
            raise AssertionError("claim_turn should have raised")
        except OperationalError:
            pass

        assert "id" in seen_run_id
        assert get_handle(seen_run_id["id"]) is None

        with db_session.SessionLocal() as session:
            assert (
                session.scalar(select(ChatRun).where(ChatRun.status == "running"))
                is None
            )
    finally:
        orch._claim_after_register_before_commit = None


def test_concurrent_claims_preserve_one_running_and_409(db_client):
    """D. Concurrent claims → exactly one winner; loser is RunInProgressError."""
    from pcc.services import chat_orchestrator as orch
    from pcc.services.chat_abort import get_handle, unregister_run

    conv = _create_conversation(db_client)
    conv_id = uuid.UUID(conv["id"])
    barrier = threading.Barrier(2, timeout=5)
    winners: list = []
    losers: list = []
    lock = threading.Lock()

    def worker(label: str) -> None:
        barrier.wait()
        try:
            claim = orch.claim_turn(
                conversation_id=conv_id,
                owner_email=OWNER,
                content=f"claim-{label}",
            )
            with lock:
                winners.append(claim)
        except orch.RunInProgressError as exc:
            with lock:
                losers.append(exc)

    threads = [
        threading.Thread(target=worker, args=("a",), daemon=True),
        threading.Thread(target=worker, args=("b",), daemon=True),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()

    assert len(winners) == 1
    assert len(losers) == 1
    claim = winners[0]
    assert get_handle(claim.run_id) is not None

    with db_session.SessionLocal() as session:
        running = session.scalars(
            select(ChatRun).where(ChatRun.status == "running")
        ).all()
        assert len(running) == 1
        assert running[0].id == claim.run_id

    unregister_run(claim.run_id)


def test_normal_completion_removes_handle_and_leaves_terminal(db_client):
    """E. Successful stream unregisters the handle and leaves a terminal run."""
    from pcc.services.chat_abort import get_handle
    from pcc.services.chat_orchestrator import claim_turn, iter_sse_for_claim

    conv = _create_conversation(db_client)
    claim = claim_turn(
        conversation_id=uuid.UUID(conv["id"]),
        owner_email=OWNER,
        content="hello complete",
    )
    assert get_handle(claim.run_id) is not None
    body = "".join(iter_sse_for_claim(claim))
    assert "message_end" in body or "content_delta" in body
    assert get_handle(claim.run_id) is None

    with db_session.SessionLocal() as session:
        run = session.get(ChatRun, claim.run_id)
        assert run is not None
        assert run.status == "completed"
        assert session.scalar(select(ChatRun).where(ChatRun.status == "running")) is None


def test_recovery_skips_terminal_run_during_finalize_cleanup(db_client):
    """Recovery must not disturb a run already finalized (vs handle cleanup)."""
    from pcc.services.chat_abort import get_handle, register_run, unregister_run
    from pcc.services.chat_orchestrator import StreamOutcome, claim_turn, finalize_turn
    from pcc.services.chat_recovery import recover_abandoned_runs_locked

    conv = _create_conversation(db_client)
    claim = claim_turn(
        conversation_id=uuid.UUID(conv["id"]),
        owner_email=OWNER,
        content="finalize race",
    )
    assert get_handle(claim.run_id) is not None

    # Simulate stream completion: terminal DB state while handle still present,
    # then recovery, then unregister (mirrors finalize_turn → unregister order).
    finalize_turn(
        claim=claim,
        outcome=StreamOutcome(
            content="done",
            usage=None,
            message_status="complete",
            run_status="completed",
            cancel_reason=None,
            error_code=None,
            error_message=None,
            finish_reason="stop",
        ),
    )
    assert get_handle(claim.run_id) is not None  # not unregistered yet

    with db_session.SessionLocal() as session:
        recovered = recover_abandoned_runs_locked(
            session, conversation_id=uuid.UUID(conv["id"])
        )
        session.commit()
        assert recovered == []
        run = session.get(ChatRun, claim.run_id)
        assert run is not None
        assert run.status == "completed"

    unregister_run(claim.run_id)
    assert get_handle(claim.run_id) is None

    # After handle cleanup, still not "abandoned" because status is terminal.
    with db_session.SessionLocal() as session:
        recovered = recover_abandoned_runs_locked(
            session, conversation_id=uuid.UUID(conv["id"])
        )
        session.commit()
        assert recovered == []
        assert session.get(ChatRun, claim.run_id).status == "completed"

    # Sanity: register without running row must not invent recoveries.
    register_run(claim.run_id)
    unregister_run(claim.run_id)
