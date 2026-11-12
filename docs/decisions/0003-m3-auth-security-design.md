# ADR 0003 — Milestone 3.1 authentication and API security design

**Status:** Accepted for Milestone 3.1 planning (implementation pending)
**Date:** 2026-11-12

## Context

PCC currently has no authentication or authorization. The web app (Next.js App Router) calls FastAPI server-side, and capture endpoints are unauthenticated. Milestone 3 requires private deployment with HTTPS, protected UI/API access, and a design that can support future remote clients (including a possible ChatGPT integration path in Milestone 4).

The owner selected Google sign-in for the first authenticated release.

## Verified compatibility with the current repository stack

- Web framework: Next.js `^15.3.0` with React `^19.0.0` in `apps/web/package.json`.
- Runtime expectation: Node 22 LTS in `README.md` prerequisites.
- Routing model: App Router + Server Actions (already in use for capture flow).
- Current auth dependencies: none (no conflicting auth library already installed).

Decision: adopt an established Next.js authentication library, preferring Auth.js, because it is compatible with the current App Router model and Google OAuth provider integration pattern.

## Decision

### 1) User authentication (single-user Google sign-in)

- Use Auth.js in the Next.js app for browser authentication and session management.
- Allow sign-in only for an explicit Google account allowlist (initially exactly one account).
- Deny all other Google identities even if OAuth succeeds.

### 2) Browser session security

- Use secure, HTTP-only session cookies.
- Enforce `Secure` in production with HTTPS.
- Use `SameSite=Lax` (or stricter if no required cross-site flow is broken).
- Keep session TTL bounded and support forced sign-out by invalidating server-side session state.

### 3) API authorization boundaries (FastAPI-enforced)

- FastAPI enforces authorization for all non-health capture endpoints.
- Next.js calls FastAPI with a server-side service credential (never exposed to browser clients).
- Direct API clients use scoped bearer API tokens (for future integrations).
- API tokens are revocable and auditable (store hashed token values, not plaintext).

### 4) Service-to-service auth (Next.js -> FastAPI)

- Start with a securely managed service credential (shared secret or equivalent server-only credential), rotated by procedure.
- Do not require short-lived service JWT in Milestone 3.1 unless deployment topology expands trust boundaries.
- Keep auth middleware extensible so service JWT can be introduced later without endpoint redesign.

### 5) Deployment baseline

- Private initial deployment with HTTPS terminator/reverse proxy.
- No unauthenticated write endpoints on public interfaces.
- Secrets are server-side only and managed via deployment environment configuration, not committed files.

## Security boundaries

1. **Browser boundary:** browser holds only session cookie; no service credential or raw API token is shipped to client JS.
2. **Web server boundary (Next.js):** validates user session and account allowlist; performs server-side API calls.
3. **API boundary (FastAPI):** treats all callers as untrusted until auth is verified; enforces scope checks.
4. **Credential boundary:** service credential and token-signing material remain server-only.
5. **Network boundary:** HTTPS required at ingress; internal service traffic stays on private network path where possible.

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

## Implementation sequence (documentation-level plan)

1. Add Auth.js with Google provider and strict allowlist enforcement in the Next.js auth callback path.
2. Add protected routes/pages and session-aware server actions.
3. Add FastAPI auth middleware/dependencies and scope checks for capture endpoints.
4. Add server-side service credential verification between Next.js and FastAPI.
5. Add scoped API token model (issue/list/revoke) for future integrations.
6. Add deployment hardening (HTTPS, secret management, auth config, health/readiness checks).
7. Run Milestone 3 acceptance checks and document results in handoff/roadmap.

## Acceptance criteria for Milestone 3.1

- Only the allowlisted Google account can sign in.
- Non-allowlisted Google accounts are denied and cannot access protected UI routes.
- Browser sessions use secure HTTP-only cookies; production runs over HTTPS.
- `POST /api/v1/captures` and `GET /api/v1/captures` require valid authorization and reject unauthenticated requests.
- Next.js -> FastAPI calls succeed only with the configured service credential.
- API token scopes are enforced; revoked tokens fail immediately.
- No service credential or sensitive auth secret appears in browser-visible code or network payloads.

## Unresolved dependencies and follow-up decisions

1. Exact private deployment model for v0.1 (VPN-only/private ingress vs public HTTPS endpoint with strict auth).
2. Operational secret rotation cadence and emergency key revocation process.
3. Token scope taxonomy for initial non-browser integrations.
4. Rate-limiting thresholds and abuse controls per auth principal/token.
5. Milestone 4 feasibility gate outcomes for ChatGPT:
   - Supported integration mechanism for the target account/plan.
   - Whether that mechanism works in the standard ChatGPT iPhone app.
   - Required auth method (API key, OAuth, or other).
   - Required network reachability (for example, public HTTPS callback/tool endpoint).

Until those Milestone 4 feasibility checks are verified, do not assume iPhone support for custom ChatGPT integration.
