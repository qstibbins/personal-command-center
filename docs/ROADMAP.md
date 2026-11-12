# Personal Command Center (PCC) — Development Roadmap

**Last updated:** 2026-11-12 (priorities confirmed; Milestones 3–5 restructured)  
**Status convention:** `Verified` = supported by reported tests/observed behavior; `Implemented, awaiting acceptance` = code reportedly changed but not browser-verified; `Planned` = not yet delivered. Confirm against Git and the running app before closing a milestone.

## Delivery strategy

Ship a **secure, privately deployed capture-and-Inbox v0.1** before building sophisticated AI agents. Keep the PCC website as a direct capture interface. Treat ChatGPT mobile interaction and historical data ingestion as important future requirements, but do not assume an integration exists before verifying it.

Priorities below reflect the agreed sequence, not the order in which ideas were discussed.

### Confirmed priority (2026-11-12)

**Universal Capture v1 is complete** (Milestones 0–2, merged to `main` as PR #1, `636c026`). The agreed order of work from here:

| Milestone | Focus | Depends on |
|---|---|---|
| 3 | Authentication, API security, and minimal private deployment, designed for future remote access | Universal Capture v1 |
| 4 | ChatGPT ↔ PCC integration; first goal: create a capture from the standard ChatGPT iPhone app and see it in PCC's Inbox | Milestone 3, **and** the Milestone 4 feasibility gate |
| 5 | Task, project, and knowledge capabilities | Milestone 3 (protected API); benefits from Milestone 4 as an input channel |
| 6 | Historical conversation ingestion and knowledge review | Milestone 3; builds on Milestone 5 knowledge/task structures |
| 7 | Background processing, AI agent orchestration, and monitoring | Milestones 3 and 5 (real records to act on); Milestone 6 optional input |

**Renumbering note (nothing was dropped).** Before this update, Milestone 3 (authentication and production readiness) and Milestone 4 (first private deployment) were separate; their full scope is now combined in the new Milestone 3. The former Milestone 5 (ChatGPT integration) is now Milestone 4. The new Milestone 5 (task, project, and knowledge capabilities) draws on the product domains in `docs/PROJECT.md` and, previously, appeared only inside Milestones 6 and 7. Milestones 6 and 7 keep their numbers and scope. `docs/ARCHITECTURE.md` and `docs/PROJECT.md` were reconciled to the new numbering on 2026-11-12.

## Milestone 0 — Foundation and first vertical slice

**Status: Verified in earlier local development; verify Git state as needed.**

- Next.js 15 / React 19 frontend, FastAPI backend, PostgreSQL, Redis/RQ, Docker Compose, Alembic, SQLAlchemy, pnpm, uv.
- API endpoints: `GET /api/v1/health`, `POST /api/v1/captures`, `GET /api/v1/captures`.
- Capture persistence and Inbox display.
- Six backend tests passed with an isolated `pcc_test` database.
- User successfully created a capture through the browser and saw it in the Inbox.
- Work on branch `feature/universal-capture`; user reported pushing the earlier code and handoff documentation.

**Remaining verification:** Confirm persisted data after reload/restart when doing deployment acceptance.

## Milestone 1 — Reliable Capture UX

**Status: Verified (implemented, committed, and browser-accepted).**

Delivered in `apps/web/app`: `actions.ts` (action-state handling, returned errors/input), `capture-state.ts`, `capture-form.tsx` (`useActionState`, pending, success, error, reset), `page.tsx`, `styles.css`, `actions.test.ts`.

### Acceptance checklist

- [x] Submit a valid text capture and see the item in the Inbox.
- [ ] Observe disabled/"Saving…" state where timing permits. _Not observed in the browser (too brief locally); covered by code only._
- [x] See success feedback; form clears **only on success**.
- [x] Submit a second capture without reloading; behavior remains correct.
- [ ] Submit whitespace-only content; error is shown and input preserved. _Unit-tested only; not run in the browser._
- [x] Simulate an API/network failure; error is shown and input preserved.
- [x] `*.tsbuildinfo` is ignored in `.gitignore`.
- [x] Review diff; commit and push verified work.
- [x] Update `docs/HANDOFF.md` with the real outcome.

## Milestone 2 — Capture validation and frontend coverage

**Status: Verified (implemented, committed, and browser-accepted on 2026-11-12).**

Decisions:
- FastAPI is authoritative. Titles and content are trimmed at the API; blank content is rejected.
- URL captures: absolute `http`/`https` only with a valid host; embedded credentials rejected; max 2,048 chars; the trimmed original string is stored (no normalization). Remote content fetching is **out of scope**.
- Text captures: max 100,000 chars; never URL-checked; internal whitespace and line breaks preserved.
- The Server Action maps expected 422s to field-level errors and uses generic messages for network, 5xx, or malformed responses; user input is preserved on failure and the form resets only on success. URL rules are not duplicated in the frontend.

Delivered:
- [x] Define URL capture semantics.
- [x] Implement validation (API) and field-level error display (frontend).
- [x] Tests: backend 61/61 with a Postgres `pcc_test` DB; frontend Server Action tests 27/27.
- [x] Re-run typecheck, tests, build, and browser checks (invalid URL, correction without reselecting Type, text capture, backend down, success reset).
- [x] Fix the regression found in acceptance: the Type select reset to Text after a failed submit.
- [x] Commit and update handoff.

**Remaining gap:** no component-level automated regression coverage (only the Server Action is unit-tested). Form behavior is verified manually in a browser. No jsdom/Testing Library or browser test tool has been added.

**Exit criterion met:** users get clear feedback for invalid inputs; accepted data is persisted correctly; Server Action and API regressions are covered.

## Predeployment stabilization (before or alongside Milestone 3)

**Status: Mostly done in PR #1; a few items remain.** See the Project store `docs/predeployment-stabilization-notes.md`.

- [x] Fix the 19 pre-existing backend Ruff errors (CI `ruff check src tests` passes).
- [x] Add a `pnpm test:web` step to the CI frontend job.
- [x] Add a Postgres service and `TEST_DATABASE_URL` (`pcc_test`) to the CI backend job so DB-backed tests run; all API tests now go through the isolated `db_client` fixture.
- [ ] Decide on component-level / browser regression coverage for the capture form (none exists; only the Server Action is unit-tested).
- [ ] Refresh remaining stale docs and `.env.example`; use `--frozen-lockfile` in CI.

## Milestone 3 — Authentication, API security, and minimal private deployment

**Status: In progress. Milestone 3.1 (ADR) complete; Milestone 3.2 (FastAPI service-credential auth + scopes) complete; Milestone 3.3 (Auth.js v5 Google sign-in, PostgreSQL database sessions, page/Server Action protection) complete in code — real Google OAuth browser acceptance still required; Milestone 3.4 (scoped/revocable API tokens) complete in code. Remaining for Milestone 3: private deployment.** This milestone combines the former Milestone 3 (authentication and production readiness) and Milestone 4 (first private deployment, v0.1).

**Design constraint: designed for future remote access.** The first deployment may be minimal and private, but it must not assume that the only client is a browser on the same machine. Choices made here should keep a later internet-reachable, HTTPS-protected endpoint possible without redesign. ChatGPT iPhone feasibility remains a **Milestone 4 gate**, not a Milestone 3 completion requirement. In particular: no hard-coded `localhost` assumptions, configurable public/internal base URLs and allowed origins, and API authentication that a non-browser client can use.

### Architecture assessment (Milestone 3.1 — complete)
- [x] Choose a simple authentication approach appropriate for a single-user private deployment (website sign-in plus API credentials), and record it as a decision under `docs/decisions/` (`0003-m3-auth-security-design.md`): Google sign-in, Auth.js v5 with PostgreSQL database sessions, FastAPI-enforced authorization, server-side Next.js→FastAPI service credential, and scoped revocable API tokens (`captures:read`, `captures:write`) for future integrations.
- [x] Decide how the Next.js server authenticates to FastAPI and how non-browser clients authenticate: server-side service credential for Next.js→FastAPI plus scoped/revocable bearer API tokens for future integrations (see `docs/decisions/0003-m3-auth-security-design.md`).
- [ ] Choose the hosting target and network exposure model (small VPS + Docker Compose is a candidate, not a final decision; private-only versus a public HTTPS endpoint with auth).
- [ ] Inventory what production needs that does not exist yet: Dockerfiles, production config, secrets handling, deep health checks, request size limits and rate limiting, CORS/origin policy, migration procedure, backups.

### Authentication and API security
- [x] **Milestone 3.2:** Protect capture API endpoints with FastAPI auth (`captures:read` / `captures:write`); Next.js server sends `PCC_SERVICE_CREDENTIAL` as a Bearer token (never to the browser). Health remains public. Auth module is centralized for future API tokens.
- [x] **Milestone 3.3:** Protect website access (Auth.js v5 + Google verified-email allowlist + PostgreSQL database sessions) and Server Actions with server-side session checks (ADR 0003). Sign-out deletes the Auth.js `sessions` row. Local setup: `docs/google-signin-local.md`. _Browser OAuth acceptance with a real Google client still pending._
- [x] Document service-credential and Auth.js / Google OAuth environment variables for local development (`.env.example`, README, `docs/google-signin-local.md`); keep secrets server-only.
- [ ] Configure remaining production secrets and Auth.js / Google OAuth variables for the private deployment.
- [x] **Milestone 3.4:** Personal / integration API token issuance (hashed SHA-256 storage, scopes `captures:read` / `captures:write`, revocable/expiring, owner-only create/list/revoke via allowlisted Auth.js session + FastAPI service-credential management routes). Raw token shown once. ChatGPT wiring remains Milestone 4.

### Minimal private deployment (v0.1)
- [ ] Select hosting and configure HTTPS, domain/access, persistent PostgreSQL storage, and backups.
- [ ] Verify production builds, the database migration procedure, and health checks; run migrations and start services with production configuration.
- [ ] Verify sign-in, capture, Inbox retrieval, refresh, service restart, and data persistence.
- [ ] Verify backup/recovery and document repeatable deploy, rollback, recovery, and access steps.

**Exit criterion:** PCC is deployed at a secure private URL without exposing personal captures or unauthenticated write endpoints, the capture workflow survives a restart, and nothing in the design blocks later remote access.

**Open Milestone 3 implementation dependencies (not ChatGPT iPhone feasibility):** final private ingress model (VPN/private endpoint vs public HTTPS + strict auth), and operational secret-rotation cadence. Auth.js tables are owned by Alembic revision `0003_authjs_tables` (resolved in Milestone 3.3). ChatGPT iPhone support, auth method, and reachability remain **Milestone 4 feasibility-gate** items and are not required to close Milestone 3.

## Milestone 4 — ChatGPT ↔ PCC integration

**Status: Planned; blocked on the feasibility gate and Milestone 3.** (Formerly Milestone 5.)

**First goal:** create a capture from the standard ChatGPT iPhone app and see it in PCC's Inbox.

### Feasibility gate (complete and record before any implementation)
Do not assume that custom MCP or tool support works in the standard iPhone client. Verify against current OpenAI documentation and an actual device and account, and record the findings:
- [ ] **Supported mechanism:** what integration types the standard ChatGPT app supports for this account/plan (for example custom connectors, MCP servers, or GPT Actions), and which is appropriate for "save capture".
- [ ] **Mobile availability:** whether that mechanism actually works in the standard ChatGPT iPhone app, not only on web or desktop.
- [ ] **Authentication requirements:** what auth the mechanism requires (for example OAuth versus API key), and how it maps to PCC's Milestone 3 authentication.
- [ ] **Network accessibility:** what reachability ChatGPT requires (for example a public HTTPS endpoint), and whether that is compatible with the Milestone 3 exposure model.
- [ ] If unsupported, record the limitation and choose an alternative without claiming parity with other assistants.

### Implementation (only after the gate passes)
- [ ] Define minimal authorized operations, starting with save capture, then retrieve selected information.
- [ ] Implement authenticated PCC-facing tool endpoints or an adapter appropriate to the verified mechanism.
- [ ] Test end-to-end from an actual supported ChatGPT client (the iPhone app); verify permissions and error handling.

**Exit criterion:** If supported, an instruction issued from the standard ChatGPT iPhone app creates a capture that appears in PCC's Inbox. If unsupported, the limitation is recorded and an alternative is chosen.

## Milestone 5 — Task, project, and knowledge capabilities

**Status: Planned. Scope to be detailed before starting.** (New milestone; consolidates product domains from `docs/PROJECT.md`.)

- [ ] Review and promote captures into tasks and projects (a capture is not automatically a task).
- [ ] Task and project data model, API, and UI, with review before inferred tasks become commitments.
- [ ] Knowledge search, retrieval, and linking that retain originals and provenance.
- [ ] Keep distinctions between speculation, confirmed decisions, and approved actions.

**Dependencies:** a protected API (Milestone 3). Milestones 6 and 7 build on these records.

**Exit criterion:** Captures can be organized into projects and tasks and found again, with traceable provenance. Detailed acceptance criteria to be written when the milestone starts.

## Milestone 6 — Historical conversation ingestion and knowledge review

**Status: Planned.** Depends on Milestone 3; the review/extraction steps build on the Milestone 5 task, project, and knowledge structures.

- [ ] Inspect a real ChatGPT export and define supported import format(s).
- [ ] Import conversations with timestamps, titles, messages, and source provenance when available.
- [ ] Make imports repeatable/idempotent and protect sensitive data.
- [ ] Add reviewable extraction of decisions, candidate tasks, projects, and useful knowledge.
- [ ] Preserve distinctions between speculation, confirmed decisions, and approved actions.

**Exit criterion:** Imported material is retrievable and traceable to its source; derived records can be reviewed rather than silently accepted.

## Milestone 7 — Background processing, agents, and observability

**Status: Planned.** AI agent orchestration and monitoring. Depends on Milestone 3 and on real records to act on (Milestone 5); historical import (Milestone 6) is an optional input.

- [ ] Use Redis/RQ for reliable background processing of captured material.
- [ ] Introduce AI provider abstraction, budgets, logging, and appropriate data handling.
- [ ] Define agent, thread/workstream, and run records based on actual execution needs.
- [ ] Implement specialized workflows incrementally (e.g., capture classification or briefing).
- [ ] Expose run status, history, outputs, errors, and approvals in the PCC website.
- [ ] Add safe retry, cancellation, and permission controls as required.

**Exit criterion:** At least one real workflow runs asynchronously, persists results, and is inspectable in the dashboard. Expand to additional agents only after this foundation works.

## Documentation and development workflow

At the end of each bounded feature:
1. Cursor inspects the actual repository and implements only the agreed scope.
2. Run relevant tests/builds and perform browser acceptance where applicable.
3. Review the diff and resolve issues before committing.
4. Commit/push with explicit user approval.
5. Update `docs/HANDOFF.md` (current truth and next action) and `docs/ROADMAP.md` (milestone status). Update `PROJECT.md` only for product changes and `ARCHITECTURE.md` for architectural changes.

**Do not let a new conversation, tool failure, or speculative feature discussion silently reorder the roadmap.**

## Known nonblocking issue

The Python editable-install `.pth` file may intermittently receive the macOS `hidden` flag and cause import failures. The cause remains unverified; `PYTHONPATH=src` has been used as a targeted workaround. Do not reopen this investigation unless it blocks the current task. See `docs/HANDOFF.md`.
