"""Opaque API token generation and hashing (ADR 0003).

Raw tokens are shown once at creation. Only SHA-256 hashes are persisted.
"""

from __future__ import annotations

import hashlib
import secrets

# Distinct prefix so operators can recognize PCC integration tokens.
TOKEN_PREFIX = "pcc_at_"
# secrets.token_urlsafe(32) → 43 chars; full raw token stays under common header limits.
_TOKEN_SECRET_BYTES = 32
# Non-secret prefix shown in list UI (includes the pcc_at_ marker + a short slice).
_DISPLAY_PREFIX_LEN = 12


def generate_api_token() -> tuple[str, str, str]:
    """Return (raw_token, token_hash, display_prefix). Never persist raw_token."""
    raw = f"{TOKEN_PREFIX}{secrets.token_urlsafe(_TOKEN_SECRET_BYTES)}"
    return raw, hash_api_token(raw), raw[:_DISPLAY_PREFIX_LEN]


def hash_api_token(raw_token: str) -> str:
    """One-way hash suitable for high-entropy opaque bearer tokens."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
