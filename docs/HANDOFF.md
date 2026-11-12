# Personal Command Center — Development Handoff

_Last updated: 2026-11-12. Universal Capture v1 (Milestones 1 and 2) is complete on `feature/universal-capture` and browser-accepted. Verify against the local repository before treating any item as complete._

## Project goal
Build PCC as a persistent personal system of record: captures, knowledge, tasks, projects, agent workflows, and outputs. Use both its own website (capture and dashboards) and, where supported, existing AI assistant apps (e.g., ChatGPT) as conversational interfaces. Preserve and eventually import useful historical ChatGPT conversations; do not assume automatic access to ChatGPT history or memory.

## Local environment
- Repo: `/Users/quinton/Desktop/srccode/personal-command-center`
- Feature branch last reported: `feature/universal-capture`
- Stack: Next.js 15 / React 19 (`apps/web`); FastAPI / Python (`apps/api`); PostgreSQL; Redis; RQ; SQLAlchemy; Alembic; Docker Compose; pnpm; uv.
- Root compose file: `compose.yaml` (not `docker-compose.yml`).
- API routes: `GET /api/v1/health`, `POST /api/v1/captures`, `GET /api/v1/captures`.
- Capture model: UUID ID, source_type `text|url`, optional title, content, status, timestamps.

## Last confirmed working
- Backend API, capture persistence, migrations, and isolated `pcc_test` test database.
- **Milestone 1 (capture UX) and Milestone 2 (capture validation) complete and committed** on `feature/universal-capture` (PR into `main`: "feat: Universal Capture v1").
- Automated checks at the final commit: `pnpm lint:web` (typecheck), `pnpm test:web` 27/27 (Server Action tests), `pnpm build:web`, and backend `uv run pytest` 61/61 with `TEST_DATABASE_URL` pointing at `pcc_test` (39 pass and 22 DB tests error without it, by design).
- **Browser acceptance passed** in real Chrome against a dev database (full stack: Next dev, uvicorn, local Postgres):
  - Invalid URL shows a field-level error under Content and keeps title, content and Type; correcting the URL without reselecting Type saves as `url`, appears in the Inbox, and resets the form (Type back to Text).
  - Text capture saves; multi-line content renders in the Inbox.
  - With FastAPI stopped, a generic error is shown ("Unable to reach the capture service. Your input was kept; try again.") and input including Type=URL is kept; after restarting FastAPI the same input saves.
  - The success message clears as soon as the user starts a new capture.
- Capture rules (enforced in FastAPI, the authority): title and content trimmed; URL captures accept only absolute `http`/`https` URLs with a valid host, no embedded username/password, max 2,048 chars; text max 100,000 chars; the trimmed original URL is stored (no normalization); remote content is never fetched. The Next.js Server Action maps 422s to field errors and uses generic messages for network/5xx/malformed responses.
- A real bug found during acceptance (the Type select reset to Text after a failed submit, so a corrected URL could save as text) is fixed: the select is remounted for each action result.

## Known gaps and predeployment work (not blockers for the PR)
Details: Project store `docs/predeployment-stabilization-notes.md`.
1. **Backend Ruff fails**: 19 pre-existing errors (11 I001, 5 UP017, 2 B008, 1 F401; 17 auto-fixable). CI runs `ruff check src tests`, so the CI backend job fails regardless of tests.
2. **CI does not run frontend tests**: no `pnpm test:web` step.
3. **CI backend job has no Postgres service or `TEST_DATABASE_URL`**: the 22 DB-backed tests error in CI. Needs a `postgres` service with a `pcc_test` database.
4. **No component-level automated regression coverage.** Only the Server Action is unit-tested (Vitest, node environment). The Type-select reset bug, field-error rendering, and form reset-on-success are covered only by manual browser checks; adding jsdom/Testing Library or a browser test tool was deliberately deferred.
5. Minor: multi-line text is stored with CRLF line endings (browser form normalization); not addressed.
6. Not browser-tested: the "Saving..." pending state and whitespace-only content (covered by unit tests only).
7. Other stale docs/CI notes (`ARCHITECTURE.md` validation section, `.env.example`, `pnpm install --no-frozen-lockfile`) are listed in the stabilization notes.

## Next
1. Merge the PR once reviewed (CI backend/lint failures are the known pre-existing items above).
2. Predeployment stabilization: fix the Ruff errors and CI gaps above.
3. Milestone 3: authentication and production readiness.

## Deployment sequence
1. ~~Finish capture UX and tests.~~ Done (Milestones 1 and 2); CI/Ruff cleanup remains predeployment work.
2. Secure access/authentication and protect API endpoints; manage secrets and production configuration.
3. Deploy a private v0.1 (small VPS / Docker Compose candidate), HTTPS, persistent Postgres, backups, migrations, health checks.
4. Verify capture persistence, authentication, service restarts, and recovery.
5. Then prioritize ChatGPT↔PCC integration feasibility, ChatGPT export ingestion, knowledge extraction/review, and agent workflows.

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
"We are continuing my Personal Command Center project. Read the attached `PCC_HANDOFF.md` first. The repo is on my Mac at `/Users/quinton/Desktop/srccode/personal-command-center`. Do not assume the handoff is verified: start by checking the relevant local files or ask me for their contents. Milestones 1 and 2 (capture UX and validation) are done; start with the predeployment CI/Ruff cleanup, then Milestone 3 (authentication). Give me one precise step at a time, with working directory and expected result. Avoid unrelated environment troubleshooting. At the end, help me update the handoff and commit." 
