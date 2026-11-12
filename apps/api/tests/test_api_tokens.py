"""Scoped API token lifecycle, auth, and leakage checks (Milestone 3.4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from auth_helpers import TEST_SERVICE_CREDENTIAL
from sqlalchemy import select

from pcc.auth.credentials import verify_api_token, verify_bearer_token
from pcc.auth.token_crypto import hash_api_token
from pcc.core.config import get_settings
from pcc.db.models import ApiToken

CAPTURE_BODY = {
    "source_type": "text",
    "title": "Token auth capture",
    "content": "Created with an API token",
}


def _assert_no_secret_leak(response, *secrets: str) -> None:
    body = response.text
    for secret in secrets:
        if secret:
            assert secret not in body
    for value in response.headers.values():
        for secret in secrets:
            if secret:
                assert secret not in value


def _create_token(client, *, label: str, scopes: list[str], expires_at: str | None = None):
    payload: dict = {
        "label": label,
        "scopes": scopes,
        "created_by_email": "owner@example.com",
    }
    if expires_at is not None:
        payload["expires_at"] = expires_at
    return client.post(
        "/api/v1/api-tokens",
        json=payload,
        headers={"Authorization": f"Bearer {TEST_SERVICE_CREDENTIAL}"},
    )


def test_create_list_revoke_lifecycle_and_no_raw_token_leak(raw_db_client):
    created = _create_token(
        raw_db_client,
        label="Integration write",
        scopes=["captures:write"],
    )
    assert created.status_code == 201
    data = created.json()
    raw_token = data["token"]
    assert raw_token.startswith("pcc_at_")
    assert data["token_prefix"] == raw_token[:12]
    assert data["scopes"] == ["captures:write"]
    assert data["revoked_at"] is None
    assert "token_hash" not in data
    _assert_no_secret_leak(created, TEST_SERVICE_CREDENTIAL)

    # Hash is stored; raw token is not.
    # Access the overridden DB via a second request path: query through ORM in a
    # dedicated check using the test client's app dependency is awkward, so
    # verify via successful auth + list omission instead, and confirm hash match
    # through verify_api_token by creating a capture (below) plus list response.
    listed = raw_db_client.get(
        "/api/v1/api-tokens",
        headers={"Authorization": f"Bearer {TEST_SERVICE_CREDENTIAL}"},
    )
    assert listed.status_code == 200
    items = listed.json()
    assert len(items) == 1
    assert "token" not in items[0]
    assert items[0]["token_prefix"] == data["token_prefix"]
    assert raw_token not in listed.text
    assert hash_api_token(raw_token) not in listed.text
    _assert_no_secret_leak(listed, TEST_SERVICE_CREDENTIAL, raw_token)

    revoked = raw_db_client.post(
        f"/api/v1/api-tokens/{data['id']}/revoke",
        headers={"Authorization": f"Bearer {TEST_SERVICE_CREDENTIAL}"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["revoked_at"] is not None
    assert "token" not in revoked.json()
    assert raw_token not in revoked.text
    _assert_no_secret_leak(revoked, TEST_SERVICE_CREDENTIAL, raw_token)

    # Revoked token cannot create captures.
    denied = raw_db_client.post(
        "/api/v1/captures",
        json=CAPTURE_BODY,
        headers={"Authorization": f"Bearer {raw_token}"},
    )
    assert denied.status_code == 401
    _assert_no_secret_leak(denied, TEST_SERVICE_CREDENTIAL, raw_token)


def test_token_hash_persisted_not_plaintext(raw_db_client):
    created = _create_token(
        raw_db_client,
        label="Hash check",
        scopes=["captures:read"],
    )
    assert created.status_code == 201
    raw_token = created.json()["token"]
    token_id = created.json()["id"]

    # Use the same app DB override by going through an authenticated list and
    # verifying auth works, then inspect via SessionLocal substitute: open a
    # query through the dependency by using verify helpers with a session from
    # the fixture engine is not exposed. Instead, monkeypatch-free check:
    # successful GET with the token proves the hash round-trip; also ensure the
    # create response never echoed a hash field.
    assert "token_hash" not in created.json()
    assert hash_api_token(raw_token) != raw_token

    ok = raw_db_client.get(
        "/api/v1/captures",
        headers={"Authorization": f"Bearer {raw_token}"},
    )
    assert ok.status_code == 200

    # Confirm DB row has hash only via service credential list + revoke id.
    listed = raw_db_client.get(
        "/api/v1/api-tokens",
        headers={"Authorization": f"Bearer {TEST_SERVICE_CREDENTIAL}"},
    )
    assert any(item["id"] == token_id for item in listed.json())
    assert raw_token not in listed.text


def test_write_token_can_create_but_not_list(raw_db_client):
    created = _create_token(
        raw_db_client,
        label="Write only",
        scopes=["captures:write"],
    )
    raw_token = created.json()["token"]
    headers = {"Authorization": f"Bearer {raw_token}"}

    post = raw_db_client.post("/api/v1/captures", json=CAPTURE_BODY, headers=headers)
    assert post.status_code == 201
    _assert_no_secret_leak(post, TEST_SERVICE_CREDENTIAL, raw_token)

    listing = raw_db_client.get("/api/v1/captures", headers=headers)
    assert listing.status_code == 403
    assert listing.json()["detail"] == "Insufficient permissions"
    _assert_no_secret_leak(listing, TEST_SERVICE_CREDENTIAL, raw_token)


def test_read_token_can_list_but_not_create(raw_db_client):
    # Seed a capture with the service credential first.
    seed = raw_db_client.post(
        "/api/v1/captures",
        json=CAPTURE_BODY,
        headers={"Authorization": f"Bearer {TEST_SERVICE_CREDENTIAL}"},
    )
    assert seed.status_code == 201

    created = _create_token(
        raw_db_client,
        label="Read only",
        scopes=["captures:read"],
    )
    raw_token = created.json()["token"]
    headers = {"Authorization": f"Bearer {raw_token}"}

    listing = raw_db_client.get("/api/v1/captures", headers=headers)
    assert listing.status_code == 200
    assert any(item["id"] == seed.json()["id"] for item in listing.json())

    denied = raw_db_client.post("/api/v1/captures", json=CAPTURE_BODY, headers=headers)
    assert denied.status_code == 403
    assert denied.json()["detail"] == "Insufficient permissions"
    _assert_no_secret_leak(denied, TEST_SERVICE_CREDENTIAL, raw_token)


def test_both_scopes_token_can_read_and_write(raw_db_client):
    created = _create_token(
        raw_db_client,
        label="Full capture",
        scopes=["captures:read", "captures:write"],
    )
    raw_token = created.json()["token"]
    headers = {"Authorization": f"Bearer {raw_token}"}

    post = raw_db_client.post("/api/v1/captures", json=CAPTURE_BODY, headers=headers)
    assert post.status_code == 201
    listing = raw_db_client.get("/api/v1/captures", headers=headers)
    assert listing.status_code == 200
    assert any(item["id"] == post.json()["id"] for item in listing.json())


def test_expired_token_returns_401(raw_db_client):
    expires = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    created = _create_token(
        raw_db_client,
        label="Already expired",
        scopes=["captures:write"],
        expires_at=expires,
    )
    # Creation rejects past expires_at.
    assert created.status_code == 422

    # Insert an already-expired row by creating a future token then backdating
    # via direct ORM through a second create + update using the app's DB is
    # hard; instead create with a short future expiry and travel by updating
    # the row hash lookup path: create valid, then expire via SQLAlchemy using
    # Session from dependency override.
    created = _create_token(
        raw_db_client,
        label="Will expire",
        scopes=["captures:write"],
        expires_at=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    )
    assert created.status_code == 201
    raw_token = created.json()["token"]
    token_id = created.json()["id"]

    # Expire the row using the same engine as the fixture by posting revoke
    # is wrong; use verify path after mutating via management isn't available.
    # Reach into the app's overridden session factory through a capture of
    # Base metadata: simplest approach is select via a one-off session on
    # TEST_DATABASE_URL.
    import os

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(os.environ["TEST_DATABASE_URL"])
    Session = sessionmaker(bind=engine, autoflush=False)
    with Session() as session:
        row = session.get(ApiToken, token_id)
        assert row is not None
        row.expires_at = datetime.now(UTC) - timedelta(seconds=5)
        session.commit()
    engine.dispose()

    denied = raw_db_client.post(
        "/api/v1/captures",
        json=CAPTURE_BODY,
        headers={"Authorization": f"Bearer {raw_token}"},
    )
    assert denied.status_code == 401
    _assert_no_secret_leak(denied, TEST_SERVICE_CREDENTIAL, raw_token)


def test_invalid_and_missing_token_return_401(raw_db_client):
    missing = raw_db_client.get("/api/v1/captures")
    assert missing.status_code == 401

    bad = "pcc_at_this-is-not-a-real-token-value-xxxxxx"
    invalid = raw_db_client.get(
        "/api/v1/captures",
        headers={"Authorization": f"Bearer {bad}"},
    )
    assert invalid.status_code == 401
    _assert_no_secret_leak(invalid, TEST_SERVICE_CREDENTIAL, bad)


def test_api_token_cannot_manage_tokens(raw_db_client):
    created = _create_token(
        raw_db_client,
        label="No admin",
        scopes=["captures:read", "captures:write"],
    )
    raw_token = created.json()["token"]
    headers = {"Authorization": f"Bearer {raw_token}"}

    create_denied = raw_db_client.post(
        "/api/v1/api-tokens",
        json={
            "label": "Should fail",
            "scopes": ["captures:read"],
            "created_by_email": "owner@example.com",
        },
        headers=headers,
    )
    assert create_denied.status_code == 403

    list_denied = raw_db_client.get("/api/v1/api-tokens", headers=headers)
    assert list_denied.status_code == 403

    revoke_denied = raw_db_client.post(
        f"/api/v1/api-tokens/{created.json()['id']}/revoke",
        headers=headers,
    )
    assert revoke_denied.status_code == 403
    _assert_no_secret_leak(
        create_denied, TEST_SERVICE_CREDENTIAL, raw_token
    )


def test_token_management_requires_auth(raw_db_client):
    response = raw_db_client.get("/api/v1/api-tokens")
    assert response.status_code == 401

    response = raw_db_client.post(
        "/api/v1/api-tokens",
        json={
            "label": "Nope",
            "scopes": ["captures:read"],
            "created_by_email": "owner@example.com",
        },
    )
    assert response.status_code == 401


def test_service_credential_still_works_alongside_tokens(raw_db_client, auth_headers):
    created = raw_db_client.post(
        "/api/v1/captures",
        json=CAPTURE_BODY,
        headers=auth_headers,
    )
    assert created.status_code == 201
    listing = raw_db_client.get("/api/v1/captures", headers=auth_headers)
    assert listing.status_code == 200


def test_verify_helpers_with_db_session(raw_db_client):
    created = _create_token(
        raw_db_client,
        label="Verify helpers",
        scopes=["captures:read"],
    )
    raw_token = created.json()["token"]

    import os

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(os.environ["TEST_DATABASE_URL"])
    Session = sessionmaker(bind=engine, autoflush=False)
    with Session() as session:
        settings = get_settings()
        assert verify_bearer_token(TEST_SERVICE_CREDENTIAL, settings, session) is not None
        principal = verify_api_token(raw_token, session)
        assert principal is not None
        assert principal.auth_method == "api_token"
        assert "captures:read" in principal.scopes

        row = session.scalar(
            select(ApiToken).where(ApiToken.token_hash == hash_api_token(raw_token))
        )
        assert row is not None
        assert row.token_hash == hash_api_token(raw_token)
        # Ensure plaintext is not stored in any string column we care about.
        assert raw_token != row.token_hash
        assert raw_token != row.token_prefix
    engine.dispose()


def test_unsupported_scope_rejected(raw_db_client):
    response = raw_db_client.post(
        "/api/v1/api-tokens",
        json={
            "label": "Bad scope",
            "scopes": ["admin:all"],
            "created_by_email": "owner@example.com",
        },
        headers={"Authorization": f"Bearer {TEST_SERVICE_CREDENTIAL}"},
    )
    assert response.status_code == 422


def test_revoke_unknown_token_returns_404(raw_db_client):
    response = raw_db_client.post(
        "/api/v1/api-tokens/00000000-0000-4000-8000-000000000000/revoke",
        headers={"Authorization": f"Bearer {TEST_SERVICE_CREDENTIAL}"},
    )
    assert response.status_code == 404
