"""Schema-level tests for provider-neutral chat tables (Phase 1A.2 PR1).

Uses Base.metadata.create_all on isolated pcc_test (same path as other unit
tests). Alembic upgrade/downgrade coverage lives in test_chat_alembic.py.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from pcc.db.base import Base
from pcc.db.models import ChatRun, Conversation, Message, MessageUsage


@pytest.fixture
def chat_db():
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.fail("Set TEST_DATABASE_URL to the isolated pcc_test database")

    url = make_url(database_url)
    if url.database != "pcc_test":
        pytest.fail("Refusing to modify a database other than pcc_test")

    engine = create_engine(database_url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False)

    with session_factory() as session:
        yield session
        session.rollback()

    Base.metadata.drop_all(engine)
    engine.dispose()


def _conversation(**overrides) -> Conversation:
    values = {
        "id": uuid.uuid4(),
        "owner_email": "owner@example.com",
        "default_provider": "mock",
        "default_model": "mock-echo-v1",
    }
    values.update(overrides)
    return Conversation(**values)


def _message(conversation_id: uuid.UUID, sequence: int, **overrides) -> Message:
    values = {
        "id": uuid.uuid4(),
        "conversation_id": conversation_id,
        "owner_email": "owner@example.com",
        "role": "user",
        "status": "complete",
        "sequence": sequence,
        "content_text": "hello",
    }
    values.update(overrides)
    return Message(**values)


def test_create_all_exposes_chat_tables(chat_db):
    engine = chat_db.get_bind()
    names = set(inspect(engine).get_table_names())
    assert {
        "conversations",
        "messages",
        "message_usage",
        "chat_runs",
        "captures",
        "api_tokens",
    }.issubset(names)


def test_conversation_defaults_and_next_sequence(chat_db):
    conv = _conversation()
    chat_db.add(conv)
    chat_db.commit()
    chat_db.refresh(conv)

    assert conv.status == "active"
    assert conv.source == "pcc"
    assert conv.next_sequence == 1
    assert conv.title is None
    assert conv.deleted_at is None


def test_message_content_text_defaults_empty(chat_db):
    conv = _conversation()
    chat_db.add(conv)
    chat_db.flush()
    msg = Message(
        id=uuid.uuid4(),
        conversation_id=conv.id,
        owner_email="owner@example.com",
        role="assistant",
        status="streaming",
        sequence=1,
    )
    chat_db.add(msg)
    chat_db.commit()
    chat_db.refresh(msg)
    assert msg.content_text == ""


def test_message_sequence_unique_per_conversation(chat_db):
    conv = _conversation()
    chat_db.add(conv)
    chat_db.flush()
    chat_db.add(_message(conv.id, 1))
    chat_db.add(_message(conv.id, 1, content_text="dup"))
    with pytest.raises(IntegrityError):
        chat_db.commit()


def test_message_sequence_can_reuse_across_conversations(chat_db):
    a = _conversation()
    b = _conversation(owner_email="other@example.com")
    chat_db.add_all([a, b])
    chat_db.flush()
    chat_db.add_all([_message(a.id, 1), _message(b.id, 1, owner_email="other@example.com")])
    chat_db.commit()
    assert chat_db.scalar(select(Message).where(Message.conversation_id == a.id)) is not None


def test_conversation_import_source_external_id_unique(chat_db):
    chat_db.add(
        _conversation(
            source="import:chatgpt",
            source_external_id="ext-conv-1",
        )
    )
    chat_db.commit()
    chat_db.add(
        _conversation(
            source="import:chatgpt",
            source_external_id="ext-conv-1",
            owner_email="someoneelse@example.com",
        )
    )
    with pytest.raises(IntegrityError):
        chat_db.commit()


def test_conversation_null_source_external_id_allows_duplicates(chat_db):
    chat_db.add(_conversation(source_external_id=None))
    chat_db.add(_conversation(source_external_id=None, title="second"))
    chat_db.commit()
    assert len(chat_db.scalars(select(Conversation)).all()) == 2


def test_message_import_source_external_id_unique_within_conversation(chat_db):
    conv = _conversation()
    chat_db.add(conv)
    chat_db.flush()
    chat_db.add(_message(conv.id, 1, source_external_id="msg-1"))
    chat_db.commit()
    chat_db.add(_message(conv.id, 2, source_external_id="msg-1"))
    with pytest.raises(IntegrityError):
        chat_db.commit()


def test_one_running_run_per_conversation(chat_db):
    conv = _conversation()
    chat_db.add(conv)
    chat_db.flush()
    chat_db.add(
        ChatRun(
            id=uuid.uuid4(),
            conversation_id=conv.id,
            owner_email="owner@example.com",
            status="running",
            provider="mock",
            model="mock-echo-v1",
        )
    )
    chat_db.commit()
    chat_db.add(
        ChatRun(
            id=uuid.uuid4(),
            conversation_id=conv.id,
            owner_email="owner@example.com",
            status="running",
            provider="mock",
            model="mock-echo-v1",
        )
    )
    with pytest.raises(IntegrityError):
        chat_db.commit()


def test_multiple_terminal_runs_allowed(chat_db):
    conv = _conversation()
    chat_db.add(conv)
    chat_db.flush()
    for status in ("completed", "cancelled", "failed"):
        chat_db.add(
            ChatRun(
                id=uuid.uuid4(),
                conversation_id=conv.id,
                owner_email="owner@example.com",
                status=status,
                provider="mock",
                model="mock-echo-v1",
            )
        )
    chat_db.commit()
    assert len(chat_db.scalars(select(ChatRun)).all()) == 3


def test_message_usage_relationship_and_fk(chat_db):
    conv = _conversation()
    chat_db.add(conv)
    chat_db.flush()
    msg = _message(conv.id, 1, role="assistant", status="complete")
    chat_db.add(msg)
    chat_db.flush()
    usage = MessageUsage(
        message_id=msg.id,
        input_tokens=10,
        output_tokens=4,
        total_tokens=14,
        latency_ms=12,
        cost_micros=0,
    )
    chat_db.add(usage)
    chat_db.commit()

    loaded = chat_db.get(Message, msg.id)
    assert loaded is not None
    assert loaded.usage is not None
    assert loaded.usage.total_tokens == 14


def test_message_cascade_delete_removes_usage(chat_db):
    conv = _conversation()
    chat_db.add(conv)
    chat_db.flush()
    msg = _message(conv.id, 1, role="assistant", status="complete")
    chat_db.add(msg)
    chat_db.flush()
    chat_db.add(MessageUsage(message_id=msg.id, cost_micros=0))
    chat_db.commit()

    chat_db.delete(msg)
    chat_db.commit()
    assert chat_db.get(MessageUsage, msg.id) is None


def test_conversation_cascade_deletes_messages_and_runs(chat_db):
    conv = _conversation()
    chat_db.add(conv)
    chat_db.flush()
    msg = _message(conv.id, 1)
    run = ChatRun(
        id=uuid.uuid4(),
        conversation_id=conv.id,
        owner_email="owner@example.com",
        status="completed",
        provider="mock",
        model="mock-echo-v1",
    )
    chat_db.add_all([msg, run])
    chat_db.commit()
    conv_id = conv.id
    msg_id = msg.id
    run_id = run.id

    chat_db.delete(conv)
    chat_db.commit()
    assert chat_db.get(Conversation, conv_id) is None
    assert chat_db.get(Message, msg_id) is None
    assert chat_db.get(ChatRun, run_id) is None


def test_invalid_conversation_status_rejected(chat_db):
    chat_db.add(_conversation(status="bogus"))
    with pytest.raises(IntegrityError):
        chat_db.commit()


def test_invalid_message_status_rejected(chat_db):
    conv = _conversation()
    chat_db.add(conv)
    chat_db.flush()
    chat_db.add(_message(conv.id, 1, status="cancelled"))
    with pytest.raises(IntegrityError):
        chat_db.commit()


def test_partial_unique_indexes_exist(chat_db):
    rows = chat_db.execute(
        text(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname = 'public' AND indexname = ANY(:names)"
        ),
        {
            "names": [
                "uq_conversations_source_external_id",
                "uq_messages_conversation_source_external_id",
                "uq_chat_runs_one_running_per_conversation",
                "uq_messages_conversation_id_sequence",
            ]
        },
    ).scalars().all()
    assert set(rows) == {
        "uq_conversations_source_external_id",
        "uq_messages_conversation_source_external_id",
        "uq_chat_runs_one_running_per_conversation",
        "uq_messages_conversation_id_sequence",
    }
