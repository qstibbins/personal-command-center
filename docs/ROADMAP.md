# Personal Command Center (PCC) — Development Roadmap

**Last updated:** 2026-11-12  
**Status convention:** `Verified` = supported by reported tests/observed behavior; `Implemented, awaiting acceptance` = code reportedly changed but not browser-verified; `Planned` = not yet delivered. Confirm against Git and the running app before closing a milestone.

## Delivery strategy

Ship a **secure, privately deployed capture-and-Inbox v0.1** before building sophisticated AI agents. Keep the PCC website as a direct capture interface. Treat ChatGPT mobile interaction and historical data ingestion as important future requirements, but do not assume an integration exists before verifying it.

Priorities below reflect the agreed sequence, not the order in which ideas were discussed.

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

**Status: Planned.** See the Project store `docs/predeployment-stabilization-notes.md`.

- [ ] Fix the 19 pre-existing backend Ruff errors (CI runs `ruff check src tests` and currently fails).
- [ ] Add a `pnpm test:web` step to the CI frontend job.
- [ ] Add a Postgres service and `TEST_DATABASE_URL` (`pcc_test`) to the CI backend job so DB-backed tests run.
- [ ] Decide on component-level / browser regression coverage for the capture form.
- [ ] Refresh remaining stale docs and `.env.example`; use `--frozen-lockfile` in CI.

## Milestone 3 — Authentication and production readiness

**Status: Planned.**

- [ ] Choose a simple authentication approach appropriate for a single-user private deployment.
- [ ] Protect both website access and API endpoints; avoid relying on UI-only restrictions.
- [ ] Configure secrets and environment variables securely; avoid leaking credentials to the browser.
- [ ] Verify production builds, database migration procedure, and health checks.
- [ ] Document recovery, access, and deployment steps.

**Exit criterion:** PCC can be deployed without exposing personal captures or unauthenticated write endpoints.

## Milestone 4 — First private deployment (v0.1)

**Status: Planned.**

- [ ] Select hosting (small VPS + Docker Compose is a candidate, not a final decision).
- [ ] Configure HTTPS, domain/access, persistent PostgreSQL storage, and backups.
- [ ] Run migrations and start services using production configuration.
- [ ] Verify sign-in, capture, Inbox retrieval, refresh, service restart, and data persistence.
- [ ] Verify backup/recovery procedure and document repeatable deploy/rollback steps.

**Exit criterion:** PCC is accessible at a secure private URL and the capture workflow survives a restart.

## Milestone 5 — ChatGPT ↔ PCC integration

**Status: Planned; feasibility gate first.**

- [ ] Confirm what secure custom app/tool/MCP-style integration the **standard ChatGPT app**, particularly on iPhone, supports for this account and use case.
- [ ] Define minimal authorized operations, starting with save capture and retrieve selected information.
- [ ] Implement authenticated PCC-facing tool endpoints or adapter appropriate to supported integration.
- [ ] Test end-to-end from an actual supported ChatGPT client; verify permissions and error handling.

**Exit criterion:** If supported, an instruction issued from the ordinary assistant client can operate PCC and the result appears on the website. If unsupported, record the limitation and choose an alternative without claiming parity with Claude.

## Milestone 6 — Historical conversation ingestion and knowledge review

**Status: Planned.**

- [ ] Inspect a real ChatGPT export and define supported import format(s).
- [ ] Import conversations with timestamps, titles, messages, and source provenance when available.
- [ ] Make imports repeatable/idempotent and protect sensitive data.
- [ ] Add reviewable extraction of decisions, candidate tasks, projects, and useful knowledge.
- [ ] Preserve distinctions between speculation, confirmed decisions, and approved actions.

**Exit criterion:** Imported material is retrievable and traceable to its source; derived records can be reviewed rather than silently accepted.

## Milestone 7 — Background processing, agents, and observability

**Status: Planned.**

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
