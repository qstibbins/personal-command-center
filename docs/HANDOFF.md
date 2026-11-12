# Personal Command Center — Development Handoff

_Last updated: 2026-11-12. Universal Capture v1 (Milestones 0–2) is complete, browser-accepted, and merged to `main` (PR #1, `636c026`). Verify against the local repository before treating any item as complete._

## Project goal
Build PCC as a persistent personal system of record: captures, knowledge, tasks, projects, agent workflows, and outputs. Use both its own website (capture and dashboards) and, where supported, existing AI assistant apps (e.g., ChatGPT) as conversational interfaces. Preserve and eventually import useful historical ChatGPT conversations; do not assume automatic access to ChatGPT history or memory.

## Local environment
- Repo: `/Users/quinton/Desktop/srccode/personal-command-center`
- Branch: `main` (Universal Capture v1 merged as `636c026`; `feature/universal-capture` is the merged feature branch)
- Stack: Next.js 15 / React 19 (`apps/web`); FastAPI / Python (`apps/api`); PostgreSQL; Redis; RQ; SQLAlchemy; Alembic; Docker Compose; pnpm; uv.
- Root compose file: `compose.yaml` (not `docker-compose.yml`).
- API routes: `GET /api/v1/health`, `POST /api/v1/captures`, `GET /api/v1/captures`.
- Capture model: UUID ID, source_type `text|url`, optional title, content, status, timestamps.

## Last confirmed working
- Backend API, capture persistence, migrations, and isolated `pcc_test` test database.
- **Milestone 1 (capture UX) and Milestone 2 (capture validation) complete and merged to `main`** (PR #1, "feat: Universal Capture v1").
- Automated checks at the final commit: `pnpm lint:web` (typecheck), `pnpm test:web` 27/27 (Server Action tests), `pnpm build:web`, and backend `uv run pytest` 61/61 with `TEST_DATABASE_URL` pointing at `pcc_test`.
- Durable test guidance: API endpoint tests are intentionally isolated through `db_client` and require `TEST_DATABASE_URL` targeting `pcc_test`; without it, endpoint tests fail fast instead of falling back to any non-test database.
- **Browser acceptance passed** in real Chrome against a dev database (full stack: Next dev, uvicorn, local Postgres):
  - Invalid URL shows a field-level error under Content and keeps title, content and Type; correcting the URL without reselecting Type saves as `url`, appears in the Inbox, and resets the form (Type back to Text).
  - Text capture saves; multi-line content renders in the Inbox.
  - With FastAPI stopped, a generic error is shown ("Unable to reach the capture service. Your input was kept; try again.") and input including Type=URL is kept; after restarting FastAPI the same input saves.
  - The success message clears as soon as the user starts a new capture.
- Capture rules (enforced in FastAPI, the authority): title and content trimmed; URL captures accept only absolute `http`/`https` URLs with a valid host, no embedded username/password, max 2,048 chars; text max 100,000 chars; the trimmed original URL is stored (no normalization); remote content is never fetched. The Next.js Server Action maps 422s to field errors and uses generic messages for network/5xx/malformed responses.
- A real bug found during acceptance (the Type select reset to Text after a failed submit, so a corrected URL could save as text) is fixed: the select is remounted for each action result.

## Confirmed product priority (decision, 2026-11-12)
Universal Capture v1 is complete. The agreed sequence (details and dependencies in `docs/ROADMAP.md`):
1. **Milestone 3 — Authentication, API security, and minimal private deployment, designed for future remote access.** (Combines the former Milestones 3 and 4.)
2. **Milestone 4 — ChatGPT ↔ PCC integration.** First goal: create a capture from the standard ChatGPT iPhone app and see it in PCC's Inbox. **Before implementing**, verify the supported integration mechanism, mobile availability, authentication requirements, and network accessibility. Do not assume custom MCP support works in the standard iPhone client.
3. **Milestone 5 — Task, project, and knowledge capabilities** (new milestone).
4. **Milestone 6 — Historical conversation ingestion.** 5. **Milestone 7 — AI agent orchestration and monitoring.** (Numbers unchanged.)

Dependency to keep in mind: Milestone 4 likely needs an authenticated, network-reachable endpoint, so Milestone 3 must not assume a localhost-only, browser-only client. This is unverified until the Milestone 4 feasibility gate is done.

## Known gaps (not blockers)
Details: Project store `docs/predeployment-stabilization-notes.md`.
- **Resolved in PR #1:** backend Ruff errors (19), missing `pnpm test:web` CI step, missing Postgres service/`TEST_DATABASE_URL` for backend CI. CI (backend and frontend) passes. All API tests use the isolated `db_client` fixture.
- **No component-level automated regression coverage.** Only the Server Action is unit-tested (Vitest, node environment). The Type-select reset bug, field-error rendering, and form reset-on-success are covered only by manual browser checks; adding jsdom/Testing Library or a browser test tool was deliberately deferred.
- Multi-line text is stored with CRLF line endings (browser form normalization); not addressed.
- Not browser-tested: the "Saving..." pending state and whitespace-only content (unit tests only).
- Still open: `.env.example` is out of date; CI uses `pnpm install --no-frozen-lockfile`.
- Docs reconciled 2026-11-12: `ARCHITECTURE.md` and `PROJECT.md` now use the new milestone numbering and describe the merged capture implementation. `ARCHITECTURE.md` Part C still records open items (shallow health check, untested migrations, unused `projects`/`tasks` tables, `.env.example` drift).
- Future risk to design for if URLs are ever fetched server-side: accepted URLs include localhost/private hosts, so fetching would need SSRF controls.

## Immediate next step
**Finish the Milestone 3 architecture assessment** (no implementation yet). Produce a short decision record (suggested location `docs/decisions/`) covering: the single-user authentication approach for the website and API; how the Next.js server authenticates to FastAPI and how non-browser clients would authenticate; the hosting target and network exposure model; and the inventory of missing production pieces (Dockerfiles, secrets, deep health checks, request limits/rate limiting, CORS/origin policy, migrations, backups). Keep it compatible with future remote access. Then plan Milestone 3 implementation from that assessment.

## Deployment sequence
1. ~~Finish capture UX and tests.~~ Done (Universal Capture v1).
2. **Milestone 3:** architecture assessment, then authentication and API protection, secrets and production configuration.
3. **Milestone 3:** deploy a minimal private v0.1 (small VPS / Docker Compose candidate), HTTPS, persistent Postgres, backups, migrations, health checks; design for future remote access.
4. Verify capture persistence, authentication, service restarts, and recovery.
5. **Milestone 4:** verify then build ChatGPT↔PCC integration (first goal: capture from the standard ChatGPT iPhone app appears in the Inbox). Then task/project/knowledge capabilities (M5), historical ingestion (M6), and agent orchestration/monitoring (M7).

## Integration principles
- Calling OpenAI API from PCC is different from exposing PCC tools to the standard ChatGPT app.
- Desired UX: prompt in standard AI assistant mobile app; authorized tool calls operate PCC; website displays agent outputs and allows direct capture.
- Verify ChatGPT mobile support for custom integrations before promising it.
- ChatGPT subscription does not automatically grant OpenAI API credits or access to all chat history/memory.
- Keep AI provider abstraction flexible (OpenAI, other APIs, local models).

## Known environment issue — avoid reopening unless blocking
Editable Hatchling install may have a `.pth` file in `apps/api/.venv/lib/python3.12/site-packages/` acquiring macOS `hidden` flag, causing intermittent `import pcc` failures. Root cause not established. `PYTHONPATH=src uv run python ...` is a working one-off workaround. Pytest config includes `pythonpath = ["src"]`. Do not invent uv settings or divert feature work into speculative environment changes.

## Working rules for future sessions
- Use the repository, test output, and Git history as truth; this handoff is context, not verification.
- Give exact working directory, filename, and command for every action.
- One bounded implementation step at a time. Explain expected output and what failure means.
- Do not mark tasks complete without verification.
- After each completed feature: tests → browser check where relevant → commit → update this file.
- If troubleshooting becomes unrelated, record it as a separate issue and return to the milestone.

## Suggested opening message for a new chat
"We are continuing my Personal Command Center project. Read the attached `PCC_HANDOFF.md` first. The repo is on my Mac at `/Users/quinton/Desktop/srccode/personal-command-center`. Do not assume the handoff is verified: start by checking the relevant local files or ask me for their contents. Universal Capture v1 (Milestones 0–2) is done and merged. The confirmed next step is to finish the Milestone 3 architecture assessment (authentication, API security, minimal private deployment designed for future remote access); ChatGPT integration (Milestone 4) comes after, and its feasibility must be verified first. Give me one precise step at a time, with working directory and expected result. Avoid unrelated environment troubleshooting. At the end, help me update the handoff and commit." 
