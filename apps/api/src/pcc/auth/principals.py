from dataclasses import dataclass

SCOPE_CAPTURES_READ = "captures:read"
SCOPE_CAPTURES_WRITE = "captures:write"

# The Next.js service principal receives both capture scopes for the Universal
# Capture workflow. Future API tokens will carry an explicit subset.
SERVICE_CREDENTIAL_SCOPES: frozenset[str] = frozenset(
    {SCOPE_CAPTURES_READ, SCOPE_CAPTURES_WRITE}
)


@dataclass(frozen=True, slots=True)
class AuthPrincipal:
    """Authenticated caller after credential verification, before scope checks."""

    subject: str
    scopes: frozenset[str]
    auth_method: str
