"""PostgreSQL-backed chat orchestration API tests (Phase 1A.2 PR3)."""

from __future__ import annotations

import json
import uuid
from unittest import mock

from auth_helpers import TEST_SERVICE_CREDENTIAL
from sqlalchemy import select

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
