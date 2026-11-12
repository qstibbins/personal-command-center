"""Authentication and authorization for capture endpoints (Milestone 3.2)."""

from __future__ import annotations

from auth_helpers import TEST_SERVICE_CREDENTIAL

from pcc.auth.credentials import verify_api_token, verify_bearer_token
from pcc.auth.dependencies import get_principal
from pcc.auth.principals import (
    SCOPE_CAPTURES_READ,
    SCOPE_CAPTURES_WRITE,
    AuthPrincipal,
)
from pcc.core.config import get_settings
from pcc.main import app

CAPTURE_BODY = {
    "source_type": "text",
    "title": "Auth test",
    "content": "Protected capture content",
}


def _assert_no_credential_leak(response, *secrets: str) -> None:
    body = response.text
    for secret in secrets:
        if secret:
            assert secret not in body
    # Header echo / WWW-Authenticate must not include the secret either.
    for value in response.headers.values():
        for secret in secrets:
            if secret:
                assert secret not in value


def test_health_remains_unauthenticated():
    from fastapi.testclient import TestClient

    response = TestClient(app).get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "pcc-api"}


def test_missing_credentials_returns_401(raw_db_client):
    response = raw_db_client.get("/api/v1/captures")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"
    _assert_no_credential_leak(response, TEST_SERVICE_CREDENTIAL)

    response = raw_db_client.post("/api/v1/captures", json=CAPTURE_BODY)
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"
    _assert_no_credential_leak(response, TEST_SERVICE_CREDENTIAL)


def test_invalid_credentials_returns_401(raw_db_client):
    bad = "definitely-not-the-service-credential"
    headers = {"Authorization": f"Bearer {bad}"}

    response = raw_db_client.get("/api/v1/captures", headers=headers)
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"
    _assert_no_credential_leak(response, TEST_SERVICE_CREDENTIAL, bad)

    response = raw_db_client.post("/api/v1/captures", json=CAPTURE_BODY, headers=headers)
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"
    _assert_no_credential_leak(response, TEST_SERVICE_CREDENTIAL, bad)


def test_empty_bearer_token_returns_401(raw_db_client):
    response = raw_db_client.get(
        "/api/v1/captures",
        headers={"Authorization": "Bearer "},
    )
    assert response.status_code == 401
    _assert_no_credential_leak(response, TEST_SERVICE_CREDENTIAL)


def test_non_bearer_scheme_returns_401(raw_db_client):
    response = raw_db_client.get(
        "/api/v1/captures",
        headers={"Authorization": f"Basic {TEST_SERVICE_CREDENTIAL}"},
    )
    assert response.status_code == 401
    _assert_no_credential_leak(response, TEST_SERVICE_CREDENTIAL)


def test_unset_service_credential_rejects_even_matching_token(
    raw_db_client, monkeypatch
):
    """Fail closed when the server has no configured credential."""
    monkeypatch.setenv("PCC_SERVICE_CREDENTIAL", "")
    get_settings.cache_clear()

    response = raw_db_client.get(
        "/api/v1/captures",
        headers={"Authorization": f"Bearer {TEST_SERVICE_CREDENTIAL}"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"
    _assert_no_credential_leak(response, TEST_SERVICE_CREDENTIAL)


def test_previous_service_credential_accepted_during_rotation(
    raw_db_client, monkeypatch
):
    previous = "previous-service-credential-during-rotation"
    monkeypatch.setenv("PCC_SERVICE_CREDENTIAL", "current-service-credential")
    monkeypatch.setenv("PCC_SERVICE_CREDENTIAL_PREVIOUS", previous)
    get_settings.cache_clear()

    response = raw_db_client.get(
        "/api/v1/captures",
        headers={"Authorization": f"Bearer {previous}"},
    )
    assert response.status_code == 200
    _assert_no_credential_leak(
        response, previous, "current-service-credential", TEST_SERVICE_CREDENTIAL
    )


def test_authorized_list_and_create_succeed(raw_db_client, auth_headers):
    create = raw_db_client.post(
        "/api/v1/captures",
        json=CAPTURE_BODY,
        headers=auth_headers,
    )
    assert create.status_code == 201
    data = create.json()
    assert data["content"] == CAPTURE_BODY["content"]
    _assert_no_credential_leak(create, TEST_SERVICE_CREDENTIAL)

    listing = raw_db_client.get("/api/v1/captures", headers=auth_headers)
    assert listing.status_code == 200
    assert any(item["id"] == data["id"] for item in listing.json())
    _assert_no_credential_leak(listing, TEST_SERVICE_CREDENTIAL)


def test_insufficient_permissions_returns_403(raw_db_client, monkeypatch):
    """Limited-scope principal is authenticated but blocked on missing scopes."""

    limited = AuthPrincipal(
        subject="api_token:test-limited",
        scopes=frozenset({SCOPE_CAPTURES_READ}),
        auth_method="api_token",
    )
    limited_token = "limited-scope-test-token"

    def fake_api_token(token: str, db):
        if token == limited_token:
            return limited
        return None

    monkeypatch.setattr(
        "pcc.auth.credentials.verify_api_token",
        fake_api_token,
    )

    # Read scope is enough for GET.
    ok = raw_db_client.get(
        "/api/v1/captures",
        headers={"Authorization": f"Bearer {limited_token}"},
    )
    assert ok.status_code == 200

    # Write requires captures:write.
    denied = raw_db_client.post(
        "/api/v1/captures",
        json=CAPTURE_BODY,
        headers={"Authorization": f"Bearer {limited_token}"},
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "Insufficient permissions"
    _assert_no_credential_leak(
        denied, TEST_SERVICE_CREDENTIAL, limited_token
    )


def test_write_only_principal_cannot_list(raw_db_client, monkeypatch):
    write_only = AuthPrincipal(
        subject="api_token:write-only",
        scopes=frozenset({SCOPE_CAPTURES_WRITE}),
        auth_method="api_token",
    )
    token = "write-only-test-token"

    monkeypatch.setattr(
        "pcc.auth.credentials.verify_api_token",
        lambda t, db: write_only if t == token else None,
    )

    denied = raw_db_client.get(
        "/api/v1/captures",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "Insufficient permissions"

    created = raw_db_client.post(
        "/api/v1/captures",
        json=CAPTURE_BODY,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert created.status_code == 201


def test_authorized_request_still_validates_capture_body(raw_db_client, auth_headers):
    response = raw_db_client.post(
        "/api/v1/captures",
        json={"source_type": "text", "content": "   "},
        headers=auth_headers,
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "content"]
    _assert_no_credential_leak(response, TEST_SERVICE_CREDENTIAL)


def test_verify_bearer_token_prefers_service_credential(raw_db_client):
    import os

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(os.environ["TEST_DATABASE_URL"])
    Session = sessionmaker(bind=engine, autoflush=False)
    with Session() as session:
        settings = get_settings()
        principal = verify_bearer_token(TEST_SERVICE_CREDENTIAL, settings, session)
        assert principal is not None
        assert principal.auth_method == "service_credential"
        assert SCOPE_CAPTURES_READ in principal.scopes
        assert SCOPE_CAPTURES_WRITE in principal.scopes
        assert verify_api_token("not-a-real-token", session) is None
    engine.dispose()


def test_get_principal_override_cleared_after_insufficient_scope_test(raw_db_client):
    """Ensure we did not leave a get_principal bypass in place."""
    assert get_principal not in app.dependency_overrides
    response = raw_db_client.get("/api/v1/captures")
    assert response.status_code == 401
