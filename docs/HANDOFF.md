# Personal Command Center — Development Handoff

_Last updated: 2026-11-12. Universal Capture v1 (Milestones 0–2) merged; Milestones 3.1–3.4 auth/API security on `main`; Milestone 3.5a Render deployment ADR accepted (docs only). Verify against the local repository before treating any item as complete._

## Project goal
Build PCC as a persistent personal system of record: captures, knowledge, tasks, projects, agent workflows, and outputs. Use both its own website (capture and dashboards) and, where supported, existing AI assistant apps (e.g., ChatGPT) as conversational interfaces. Preserve and eventually import useful historical ChatGPT conversations; do not assume automatic access to ChatGPT history or memory.

## Local environment
- Repo: `/Users/quinton/Desktop/srccode/personal-command-center`
- Branch: work happens on feature branches; `main` includes through Milestone 3.4 (`d608cee`, PR #6). Milestone 3.5a docs land via `docs/m3-render-deployment-design`.
- Stack: Next.js 15 / React 19 (`apps/web`); FastAPI / Python (`apps/api`); PostgreSQL; Redis; RQ; SQLAlchemy; Alembic; Docker Compose; pnpm; uv; Auth.js v5 (`next-auth` beta) + `@auth/pg-adapter`.
- **Planned production host:** Render (ADR 0004) — public Next.js web service, private FastAPI, managed Postgres; Redis/worker **not** in v0.1.
- Root compose file: `compose.yaml` (not `docker-compose.yml`) — local/dev only.
- API routes: `GET /api/v1/health`, `POST|GET /api/v1/captures`, `POST|GET /api/v1/api-tokens`, `POST /api/v1/api-tokens/{id}/revoke`.
- Capture model: UUID ID, source_type `text|url`, optional title, content, status, timestamps.
- Auth.js tables (Alembic `0003_authjs_tables`): `users`, `accounts`, `sessions`, `verification_token`.
- API tokens table (Alembic `0004_api_tokens`): hashed bearer tokens with scopes, expiry, revocation.

## Last confirmed working
- Backend API, capture persistence, migrations, and isolated `pcc_test` test database.
- **Milestones 0–2** complete and merged (PR #1).
- **Milestone 3.2** FastAPI Bearer service-credential auth + scopes merged (PR #4).
- **Milestone 3.3** Auth.js v5 Google provider, PostgreSQL database sessions, verified-email allowlist, page/Server Action protection merged (PR #5).
- **Milestone 3.4** scoped API tokens merged (PR #6): opaque `pcc_at_…` tokens; SHA-256 hashes only; scopes `captures:read` / `captures:write`; owner-only create/list/revoke at `/settings/api-tokens`.
- **Milestone 3.5a (this work):** ADR 0004 — Render deployment architecture decision (documentation only; no Render resources, no Dockerfiles/`render.yaml` yet).
- Automated checks as of M3.4 on `main`: frontend tests and backend pytest/ruff green; see prior PR notes for counts. M3.5a is docs-only (no test delta required).
- Capture UX/validation and M3.2–M3.4 auth behavior remain intact in code.

## Confirmed product priority (decision, 2026-11-12)
1. **Milestone 3** — Authentication, API security, and minimal private deployment (designed for future remote access).
2. **Milestone 4** — ChatGPT ↔ PCC integration (feasibility gate first).
3. **Milestone 5** — Task, project, and knowledge capabilities.
4. **Milestone 6** — Historical conversation ingestion. 5. **Milestone 7** — AI agent orchestration and monitoring.

## Known gaps (not blockers)
- **No component-level automated regression coverage** for the capture form or token settings UI (Server Action + auth helpers are unit-tested).
- **Real Google OAuth browser acceptance** for M3.3 still required (see `docs/google-signin-local.md`).
- **Manual verification for M3.4:** sign in as allowlisted owner → create read-only and write-only tokens → confirm scope enforcement against FastAPI → revoke → confirm 401; confirm Universal Capture still works with the service credential.
- Multi-line text may store CRLF from browser form normalization.
- CI still uses `pnpm install --no-frozen-lockfile`.
- Shallow health check; migrations not covered by automated tests.
- **No production containers or Render Blueprint in repo yet** (M3.5b).

## Immediate next step
**Milestone 3.5a is complete (design).** Next is **Milestone 3.5b** per ADR 0004:

1. Containerize Next.js web + FastAPI (production Dockerfiles or equivalent Render build plans).
2. Add repo-only Render Blueprint (`render.yaml`) wiring public web → private API → Postgres; do **not** create paid resources unless the owner asks.
3. Production hardening: Postgres readiness, protect/disable `/docs`, prod env checklist (`AUTH_URL`, OAuth callbacks, service credential, internal `API_INTERNAL_URL`).
4. Migrate / backup / rollback runbook text; restore drill waits for real infra.

**Owner actions (cannot be done by agents alone):** Render account + billing, domain, live secrets, Google production OAuth URIs, first deploy, OAuth/browser acceptance, backup restore drill.

ChatGPT iPhone feasibility stays a **Milestone 4** gate. Do **not** expose FastAPI publicly “for ChatGPT,” and do **not** wire ChatGPT to API tokens until that gate passes.

## Deployment sequence
1. ~~Finish capture UX and tests.~~ Done.
2. ~~Milestone 3.1 architecture assessment.~~ Done (ADR 0003).
3. ~~Milestone 3.2 FastAPI service-credential auth + scopes.~~ Done.
4. ~~Milestone 3.3 Auth.js / Google website auth + session protection.~~ Done in code (browser OAuth acceptance pending).
5. ~~Milestone 3.4 scoped / revocable API tokens.~~ Done in code (manual token check pending).
6. ~~Milestone 3.5a Render deployment architecture.~~ Done (ADR 0004).
7. **Milestone 3.5b:** repo deploy prep (Dockerfiles, Blueprint, hardening, runbooks).
8. Owner provisions Render; migrate; verify auth, capture, restart persistence, backup/restore.
9. **Milestone 4:** verify then build ChatGPT↔PCC integration.

## Integration principles
- Calling OpenAI API from PCC is different from exposing PCC tools to the standard ChatGPT app.
- Desired UX: prompt in standard AI assistant mobile app; authorized tool calls operate PCC; website displays agent outputs and allows direct capture.
- Verify ChatGPT mobile support for custom integrations before promising it.
- ChatGPT subscription does not automatically grant OpenAI API credits or access to all chat history/memory.
- Keep AI provider abstraction flexible (OpenAI, other APIs, local models).
- ADR 0004: private FastAPI may later need a controlled public authenticated surface if Milestone 4 requires internet-reachable tools.

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
"We are continuing my Personal Command Center project. Read `docs/HANDOFF.md` first. Auth through Milestone 3.4 is on `main`; Milestone 3.5a selected Render (ADR 0004). Next: Milestone 3.5b repo deploy prep — Dockerfiles, Blueprint, deep health, runbooks — without provisioning Render unless I ask. Give me one precise step at a time."
