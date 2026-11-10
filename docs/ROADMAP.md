# Personal Command Center (PCC) — Development Roadmap

**Last updated:** 2026-11-09  
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

**Status: Implemented by Cursor; awaiting browser acceptance and commit.**

Cursor reported changes to:
- `apps/web/app/actions.ts`: action-state result handling and returned errors/input values.
- `apps/web/app/capture-state.ts`: state types/defaults.
- `apps/web/app/capture-form.tsx`: React `useActionState`, pending, success, error, reset.
- `apps/web/app/page.tsx`: uses the form component.
- `apps/web/app/styles.css`: feedback styles.
- `apps/web/app/actions.test.ts`: four action tests.

Reported checks: `pnpm lint`, `pnpm test` (4/4), and `pnpm build` passed. **Cursor explicitly did not run a browser test, commit, or push these changes.**

### Acceptance checklist

- [ ] Submit a valid text capture and see the item in the Inbox.
- [ ] Observe disabled/“Saving…” state where timing permits.
- [ ] See success feedback; form clears **only on success**.
- [ ] Submit a second capture without reloading; behavior remains correct.
- [ ] Submit whitespace-only content; error is shown and input preserved.
- [ ] Simulate an API/network failure; error is shown and input preserved.
- [ ] Address generated `apps/web/tsconfig.tsbuildinfo` ignore rule without committing build artifacts.
- [ ] Review diff; commit and push verified work.
- [ ] Update `docs/HANDOFF.md` with the real outcome.

**Current immediate action:** Perform the browser acceptance test, then review and commit. No unrelated refactoring.

## Milestone 2 — Capture validation and frontend coverage

**Status: Planned.**

- [ ] Define URL capture semantics: acceptable schemes, normalization, empty/invalid URL handling, and whether fetching remote content is in or out of scope.
- [ ] Implement consistent frontend and backend validation.
- [ ] Expand tests for valid/invalid text and URL captures and relevant form behavior.
- [ ] Re-run lint, tests, build, and focused browser checks.
- [ ] Commit and update handoff.

**Exit criterion:** Users receive clear feedback for invalid inputs; accepted data is persisted correctly; regressions are covered.

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
