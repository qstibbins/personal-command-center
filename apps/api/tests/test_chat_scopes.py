"""Chat scopes stay on the service principal; personal tokens remain capture-only."""

from typing import get_args

from pcc.auth.principals import (
    SCOPE_CAPTURES_READ,
    SCOPE_CAPTURES_WRITE,
    SCOPE_CHAT_READ,
    SCOPE_CHAT_WRITE,
    SERVICE_CREDENTIAL_SCOPES,
)
from pcc.schemas.api_token import ALLOWED_SCOPES, AllowedScope


def test_service_credential_includes_chat_scopes():
    assert SCOPE_CHAT_READ in SERVICE_CREDENTIAL_SCOPES
    assert SCOPE_CHAT_WRITE in SERVICE_CREDENTIAL_SCOPES
    assert SCOPE_CAPTURES_READ in SERVICE_CREDENTIAL_SCOPES
    assert SCOPE_CAPTURES_WRITE in SERVICE_CREDENTIAL_SCOPES


def test_personal_allowed_scope_remains_capture_only():
    assert ALLOWED_SCOPES == frozenset({SCOPE_CAPTURES_READ, SCOPE_CAPTURES_WRITE})
    assert SCOPE_CHAT_READ not in ALLOWED_SCOPES
    assert SCOPE_CHAT_WRITE not in ALLOWED_SCOPES
    assert set(get_args(AllowedScope)) == {"captures:read", "captures:write"}
