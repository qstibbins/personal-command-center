# Personal Command Center — Development Handoff

_Last updated: 2026-11-12. Universal Capture v1 (Milestones 0–2) merged; Milestone 3.1 ADR accepted; Milestone 3.2 FastAPI service-credential auth merged; Milestone 3.3 Google sign-in / Auth.js database sessions implemented on `feature/m3-google-auth`. Verify against the local repository before treating any item as complete._

## Project goal
Build PCC as a persistent personal system of record: captures, knowledge, tasks, projects, agent workflows, and outputs. Use both its own website (capture and dashboards) and, where supported, existing AI assistant apps (e.g., ChatGPT) as conversational interfaces. Preserve and eventually import useful historical ChatGPT conversations; do not assume automatic access to ChatGPT history or memory.

## Local environment
- Repo: `/Users/quinton/Desktop/srccode/personal-command-center`
- Branch: work happens on feature branches; `main` includes through Milestone 3.2 (`35fc6e3`). Milestone 3.3 lands via `feature/m3-google-auth`.
- Stack: Next.js 15 / React 19 (`apps/web`); FastAPI / Python (`apps/api`); PostgreSQL; Redis; RQ; SQLAlchemy; Alembic; Docker Compose; pnpm; uv; Auth.js v5 (`next-auth` beta) + `@auth/pg-adapter`.
- Root compose file: `compose.yaml` (not `docker-compose.yml`).
- API routes: `GET /api/v1/health`, `POST /api/v1/captures`, `GET /api/v1/captures`.
- Capture model: UUID ID, source_type `text|url`, optional title, content, status, timestamps.
- Auth.js tables (Alembic `0003_authjs_tables`): `users`, `accounts`, `sessions`, `verification_token`.

## Last confirmed working
- Backend API, capture persistence, migrations, and isolated `pcc_test` test database.
- **Milestones 0–2** complete and merged (PR #1).
- **Milestone 3.2** FastAPI Bearer service-credential auth + scopes merged (PR #4).
- **Milestone 3.3 (this work):** Auth.js v5 Google provider, PostgreSQL database sessions, verified-email allowlist (`PCC_ALLOWED_GOOGLE_EMAILS`, fail closed), `/signin` + sign-out (session row deleted), home page and `createCapture` Server Action gated server-side; M3.2 service credential preserved for Next.js→FastAPI.
- Automated checks for M3.3: `pnpm lint:web`; `pnpm test:web` **50/50** (allowlist, session gate, sign-out action, Server Action auth denial + prior capture tests); `pnpm build:web`; backend `uv run pytest` **75/75** with `TEST_DATABASE_URL` → `pcc_test`; `uv run ruff check src tests`; Alembic `upgrade head` creates Auth.js tables.
- Capture UX/validation behavior from Milestones 1–2 remains intact under an authenticated session.

## Confirmed product priority (decision, 2026-11-12)
1. **Milestone 3** — Authentication, API security, and minimal private deployment (designed for future remote access).
2. **Milestone 4** — ChatGPT ↔ PCC integration (feasibility gate first).
3. **Milestone 5** — Task, project, and knowledge capabilities.
4. **Milestone 6** — Historical conversation ingestion. 5. **Milestone 7** — AI agent orchestration and monitoring.

## Known gaps (not blockers)
- **No component-level automated regression coverage** for the capture form (Server Action + auth helpers are unit-tested).
- **Real Google OAuth browser acceptance** for M3.3 still required (see `docs/google-signin-local.md` checklist). Automated tests mock Auth.js / allowlist paths and cannot complete a live Google redirect without credentials.
- Multi-line text may store CRLF from browser form normalization.
- CI still uses `pnpm install --no-frozen-lockfile`.
- Shallow health check; migrations not covered by automated tests (manual `alembic upgrade head` verified for `0003_authjs_tables`).

## Immediate next step
**Milestone 3.3 is implemented in code** (Google/Auth.js website auth). Remaining Milestone 3 work per ADR 0003:
1. Manual browser verification with a real Google OAuth client and allowlisted account.
2. Scoped / revocable personal API token issuance (hashed storage, first issuance via authenticated control path).
3. Private HTTPS v0.1 deployment (hosting choice, secrets, backups, deep health).

ChatGPT iPhone feasibility stays a **Milestone 4** gate.

## Deployment sequence
1. ~~Finish capture UX and tests.~~ Done.
2. ~~Milestone 3.1 architecture assessment.~~ Done (ADR 0003).
3. ~~Milestone 3.2 FastAPI service-credential auth + scopes.~~ Done.
4. ~~Milestone 3.3 Auth.js / Google website auth + session protection.~~ Done in code (browser OAuth acceptance pending).
5. **Milestone 3:** API token issuance; secrets and production configuration; deploy private v0.1.
6. Verify capture persistence, authentication (including session revocation), service restarts, and recovery.
7. **Milestone 4:** verify then build ChatGPT↔PCC integration.

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
"We are continuing my Personal Command Center project. Read `docs/HANDOFF.md` first. Universal Capture v1 and Milestone 3.2 are on `main`. Milestone 3.3 (Google/Auth.js) is implemented — confirm the PR/`feature/m3-google-auth` state. Next: real Google OAuth browser acceptance, then API token issuance and private deployment per ADR 0003. Give me one precise step at a time."
