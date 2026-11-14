"""Unit tests for chat owner-email helpers (Phase 1A.2 PR1)."""

from pcc.db.models import Conversation
from pcc.services.chat_ownership import normalize_owner_email, owner_email_equals


def test_normalize_owner_email_trims_and_lowers():
    assert normalize_owner_email("  Owner@Example.COM ") == "owner@example.com"


def test_normalize_owner_email_idempotent():
    normalized = normalize_owner_email("User@Example.com")
    assert normalize_owner_email(normalized) == normalized


def test_owner_email_equals_builds_normalized_comparison():
    clause = owner_email_equals(Conversation.owner_email, "  A@B.Com ")
    # Compiled SQL should compare against the normalized literal.
    compiled = str(clause.compile(compile_kwargs={"literal_binds": True}))
    assert "a@b.com" in compiled.lower()
