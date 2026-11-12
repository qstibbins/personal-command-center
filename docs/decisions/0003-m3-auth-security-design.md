# ADR 0003 — Milestone 3.1 authentication and API security design

**Status:** Accepted. Milestones 3.2–3.4 are implemented in code; hosting/ingress for private deployment is decided in ADR 0004 (Render). Remaining Milestone 3 work is M3.5b repo deploy prep and owner provisioning.
**Date:** 2026-11-12

## Context

PCC currently has no authentication or authorization. The web app (Next.js App Router) calls FastAPI server-side, and capture endpoints are unauthenticated. Milestone 3 requires private deployment with HTTPS, protected UI/API access, and a design that can support future remote clients (including a possible ChatGPT integration path in Milestone 4).

The owner selected Google sign-in for the first authenticated release.

## Verified compatibility with the current repository stack

- Web framework: Next.js `^15.3.0` with React `^19.0.0` in `apps/web/package.json`.
- Runtime expectation: Node 22 LTS in `README.md` prerequisites.
- Routing model: App Router + Server Actions (already in use for capture flow).
- Current auth dependencies: none (no conflicting auth library already installed).
- Existing PostgreSQL 17 deployment via `compose.yaml` is available as the session store.

### Auth.js version and adapter verification

- Select **Auth.js v5** via the `next-auth` package at the v5 line (`next-auth@5` / current `next-auth@beta` publish channel). **Do not select Auth.js / NextAuth v4.**
- Auth.js v5 is App Router-first and requires Next.js ≥ 14; PCC’s Next.js 15 stack meets that requirement.
- With a database adapter configured, Auth.js defaults to the **`database` session strategy**.
- Use a PostgreSQL-compatible Auth.js v5 adapter from the `@auth/*-adapter` scope (preferred starting point: `@auth/pg-adapter` with `pg`). Adapter choice may use another official `@auth/*` Postgres-backed adapter if implementation prefers an ORM already introduced later, but the session strategy remains database-backed.
- Database sessions store an opaque session token in an HTTP-only cookie and persist session rows in PostgreSQL, which enables server-side revocation by deleting or expiring the session record.
- Implementation note: if Edge middleware/proxy is introduced and the chosen adapter is not Edge-compatible, keep session reads for protected Server Actions/pages on the Node runtime path (Auth.js documents splitting Edge-safe config from adapter config). Do not silently fall back to JWT sessions to work around that.

## Decision

### 1) User authentication (single-user Google sign-in)

- Use **Auth.js v5** in the Next.js app for browser authentication and session management.
- Allow sign-in only for an explicit Google account allowlist (initially exactly one account).
- Deny all other Google identities even if OAuth succeeds.

#### Google identity matching and allowlist storage

- Match the allowlisted identity by **verified Google account email** returned by the Google provider (case-insensitive exact match). Do not rely on display name.
- Store the allowlist as server-only configuration (environment/config), for example `PCC_ALLOWED_GOOGLE_EMAILS` (comma-separated; initially one address). Do not hard-code the address in client bundles.
- Enforce the allowlist in the Auth.js sign-in callback (and equivalent server-side session checks). A successful Google OAuth for a non-allowlisted account must not create a usable PCC session.

### 2) Browser session security (database-backed)

- Use Auth.js **database sessions** backed by PostgreSQL through a compatible Auth.js adapter.
- Persist Auth.js session tables in the same PostgreSQL instance used by PCC (schema/migrations owned by the web auth setup or coordinated Alembic/shared migration plan during implementation).
- Cookie properties:
  - HTTP-only session cookie containing the opaque session token only
  - `Secure` in production (HTTPS required)
  - `SameSite=Lax` (or stricter if no required cross-site flow is broken)
- Bounded session TTL; refresh/rotation behavior follows Auth.js database-session defaults unless a shorter max age is configured.
- **Server-side session revocation:** invalidate a session by deleting (or immediately expiring) its row in the Auth.js sessions table and clearing the cookie on sign-out. After revocation, the cookie alone is insufficient for access.

### 3) Protection surface: pages and Server Actions

- Protect both UI routes/pages **and** Server Actions. UI-only gating is insufficient.
- Server Actions that create or list captures (and any later privileged actions) must verify an authenticated, allowlisted session before calling FastAPI.
- Unauthenticated or revoked sessions must fail closed in Server Actions (no privileged FastAPI call).

### 4) API authorization boundaries (FastAPI-enforced)

- FastAPI enforces authorization for all non-health capture endpoints.
- Next.js calls FastAPI with a server-side service credential (never exposed to browser clients).
- Direct API clients use scoped bearer API tokens (for future integrations).
- API tokens are revocable and auditable (store hashed token values, not plaintext).

#### Initial API scopes

- `captures:read` — list/read captures
- `captures:write` — create captures

Additional scopes may be added later; do not invent broad `admin:*` requirements for Milestone 3.1.

#### First API token issuance

- The first integration token is issued only by an authenticated allowlisted operator through a server-side, authenticated control path (not via public unauthenticated signup and not by embedding a token in the repository or client bundle).
- On creation, show the raw token **once** to the operator; persist only a one-way hash, label, scopes, created-at, and revocation metadata.
- Default the first token to the minimum scopes needed for the intended integration path (start with `captures:write` and/or `captures:read` only).

### 5) Service-to-service auth (Next.js → FastAPI)

- Use a securely managed service credential (shared secret or equivalent server-only credential) for Next.js → FastAPI calls.
- Do not require short-lived service JWT in Milestone 3.1 unless deployment topology expands trust boundaries.
- Keep auth middleware extensible so service JWT can be introduced later without endpoint redesign.

#### Service credential compromise and rotation

- Treat compromise as an emergency: rotate the service credential immediately, redeploy/restart services that read it, and invalidate the old value so it fails verification at once.
- Prefer dual-read during planned rotation (accept current + previous briefly) only when needed for zero-downtime cutover; emergency response may cut over immediately.
- Document rotation steps in the Milestone 3 runbook (where the secret lives, how to set the new value, restart order, and verification that the old credential is rejected).

### 6) Deployment baseline

- Private initial deployment with HTTPS terminator/reverse proxy.
- No unauthenticated write endpoints on public interfaces.
- Secrets are server-side only and managed via deployment environment configuration, not committed files.
- Preserve flexibility for future ChatGPT integration by avoiding localhost-only assumptions and supporting non-browser API token auth; do **not** treat ChatGPT iPhone support as a Milestone 3 completion gate.

## Security boundaries

1. **Browser boundary:** browser holds only the opaque session cookie; no service credential or raw API token is shipped to client JS.
2. **Web server boundary (Next.js):** validates allowlisted Auth.js database session for pages **and** Server Actions; performs server-side API calls with the service credential.
3. **API boundary (FastAPI):** treats all callers as untrusted until auth is verified; enforces scope checks for service credential and API tokens.
4. **Session store boundary:** Auth.js session rows in PostgreSQL are authoritative for browser session validity; deleting a session row revokes access.
5. **Credential boundary:** service credential, Google OAuth client secret, Auth.js secret, allowlist config, and token hashes remain server-only.
6. **Network boundary:** HTTPS required at ingress; internal service traffic stays on a private network path where possible.

## Rejected alternatives

1. **Custom PCC-managed username/password auth for Milestone 3.1**
   - Rejected: higher security implementation burden (password lifecycle, reset flow, brute-force protections) with no product advantage over Google sign-in for this phase.

2. **External identity provider platform as the first step**
   - Rejected for now: adds vendor integration complexity/cost before single-user requirements demand it.
   - May be revisited for multi-user/team requirements.

3. **Perimeter-only security (network gate without API auth)**
   - Rejected: does not satisfy Milestone 3 requirement for protected API endpoints and future non-browser client support.

4. **Mandatory short-lived service JWT in Milestone 3.1**
   - Rejected for now: unnecessary complexity for current single deployment trust boundary; revisit when topology or threat model changes.

5. **Auth.js / NextAuth v4**
   - Rejected: not App Router-first for this stack; Milestone 3.1 standardizes on Auth.js v5.

6. **JWT-only Auth.js sessions without a database adapter**
   - Rejected for Milestone 3.1: weaker server-side revocation story than database sessions; PCC requires demonstrable invalidation of compromised or signed-out sessions.

## Implementation sequence (documentation-level plan)

1. Add Auth.js v5 with Google provider, PostgreSQL adapter, and `session.strategy = "database"`.
2. Enforce allowlist matching on verified Google email from server-only config.
3. Protect pages/routes **and** Server Actions with Auth.js session checks.
4. Add FastAPI auth dependencies and enforce `captures:read` / `captures:write`.
5. Add server-side service credential verification between Next.js and FastAPI, including rotation/compromise procedure.
6. Add scoped API token model (authenticated first issuance, list metadata, revoke) for future integrations.
7. Add deployment hardening (HTTPS, secret management, auth config, health/readiness checks).
8. Run Milestone 3 acceptance checks and document results in handoff/roadmap.

## Acceptance criteria for Milestone 3.1

- Only the allowlisted Google account (verified email match) can sign in.
- Non-allowlisted Google accounts are denied and cannot obtain a usable PCC session.
- Browser sessions are Auth.js database sessions in PostgreSQL; cookies are HTTP-only and `Secure` in production over HTTPS.
- Sign-out or explicit session invalidation deletes/expires the database session row; afterward, the old cookie cannot access protected pages **or** privileged Server Actions (for example capture create).
- Unauthenticated Server Action invocations fail closed and do not call FastAPI with privileged credentials.
- `POST /api/v1/captures` requires `captures:write` (or equivalent authorized service principal); `GET /api/v1/captures` requires `captures:read`; unauthenticated requests are rejected.
- Next.js → FastAPI calls succeed only with the configured service credential; a rotated-away/old credential is rejected.
- The first API token is issued only through an authenticated allowlisted control path; raw token shown once; only the hash is stored; scopes are enforced; revoked tokens fail immediately.
- No service credential or sensitive auth secret appears in browser-visible code or network payloads.

## Unresolved dependencies and follow-up decisions

These do **not** block recording Milestone 3.1 architecture decisions, but must be resolved during Milestone 3 implementation or later gates as noted:

1. ~~Exact private deployment model for v0.1 (VPN-only/private ingress vs public HTTPS endpoint with strict auth).~~ **Resolved in ADR 0004:** Render; public HTTPS Next.js + private FastAPI + managed Postgres; Redis/worker deferred.
2. Concrete operational secret-rotation cadence (beyond the emergency compromise procedure above).
3. ~~Whether Auth.js tables share the primary PCC schema via Alembic vs a dedicated web-side migration path.~~ **Resolved in Milestone 3.3:** Alembic `0003_authjs_tables`.
4. Rate-limiting thresholds and abuse controls per auth principal/token.
5. **Milestone 4 feasibility gate** (not a Milestone 3 completion requirement) for ChatGPT:
   - Supported integration mechanism for the target account/plan.
   - Whether that mechanism works in the standard ChatGPT iPhone app.
   - Required auth method (API key, OAuth, or other).
   - Required network reachability (for example, public HTTPS callback/tool endpoint).

Until those Milestone 4 feasibility checks are verified, do not assume iPhone support for custom ChatGPT integration.
