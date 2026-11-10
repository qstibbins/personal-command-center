# Personal Command Center — Development Handoff

_Last updated: 2026-11-09. Based on conversation history; verify against the local repository before treating any item as complete._

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
- Six backend tests passed with `uv run pytest -v` when `TEST_DATABASE_URL` is set to the dedicated `pcc_test` database.
- Website capture form and Inbox rendered; user submitted `My first PCC capture` and saw it listed with PENDING status; FastAPI Connected.
- TypeScript typo `rquired` fixed to `required` in `apps/web/app/page.tsx`.

## Verify first (not yet confirmed)
1. Refresh the browser and ensure the captured item remains.
2. Check `git status` and `git log -3 --oneline`; frontend commit was recommended but not confirmed.
3. Run frontend typecheck (`pnpm --dir apps/web lint`) and relevant backend tests before changing code.
4. Inspect actual files before proposing edits; never assume chat-displayed code was saved.

## Immediate next feature
Improve website capture UX: pending/loading state, clear success/error feedback, and form reset on successful save. Then URL validation and frontend tests. Keep changes narrow; verify in browser and commit.

## Deployment sequence
1. Finish capture UX and tests.
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
"We are continuing my Personal Command Center project. Read the attached `PCC_HANDOFF.md` first. The repo is on my Mac at `/Users/quinton/Desktop/srccode/personal-command-center`. Do not assume the handoff is verified: start by checking the relevant local files or ask me for their contents. Our next milestone is improving the capture form's loading, success/error, and reset behavior. Give me one precise step at a time, with working directory and expected result. Avoid unrelated environment troubleshooting. At the end, help me update the handoff and commit." 
