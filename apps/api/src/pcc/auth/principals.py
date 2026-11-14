from dataclasses import dataclass

SCOPE_CAPTURES_READ = "captures:read"
SCOPE_CAPTURES_WRITE = "captures:write"
SCOPE_CHAT_READ = "chat:read"
SCOPE_CHAT_WRITE = "chat:write"

# The Next.js service principal receives capture + chat scopes for website BFF
# calls. Personal API tokens remain capture-only (AllowedScope closed).
SERVICE_CREDENTIAL_SCOPES: frozenset[str] = frozenset(
    {
        SCOPE_CAPTURES_READ,
        SCOPE_CAPTURES_WRITE,
        SCOPE_CHAT_READ,
        SCOPE_CHAT_WRITE,
    }
)


@dataclass(frozen=True, slots=True)
class AuthPrincipal:
    """Authenticated caller after credential verification, before scope checks."""

    subject: str
    scopes: frozenset[str]
    auth_method: str
