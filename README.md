# Personal Command Center

Initial Next.js + FastAPI monorepo scaffold for a personal Second Brain and Chief of Staff. **This is a development foundation, not a production-ready app.**

## macOS prerequisites

- Git and Xcode Command Line Tools: `xcode-select --install` (if needed)
- Docker Desktop or an equivalent Docker Engine + Compose installation
- Node.js 22 LTS or compatible supported Node release
- pnpm 10 (`corepack enable` then `corepack prepare pnpm@10.11.0 --activate`, or install pnpm directly)
- Python 3.12+ and `uv` (`brew install uv`, if Homebrew is available)

## Quick start

Use several Terminal tabs (infrastructure/setup, API, web, and optionally the worker), starting from the repository root.

1. **Infrastructure**: `cp .env.example .env` then `docker compose up -d`
2. **Secrets**: set `PCC_SERVICE_CREDENTIAL` (same value for API and Next.js), `AUTH_SECRET`, Google OAuth (`AUTH_GOOGLE_ID` / `AUTH_GOOGLE_SECRET`), and `PCC_ALLOWED_GOOGLE_EMAILS` (see `.env.example` and `docs/google-signin-local.md`). Never use a `NEXT_PUBLIC_` prefix for these.
3. **Python dependencies and migrations**: `cd apps/api && uv sync --group dev && uv run alembic upgrade head` (includes Auth.js session tables)
4. **API** (same `apps/api` directory): `uv run uvicorn pcc.main:app --reload --host 127.0.0.1 --port 8000`
5. **Web** (repository root): `pnpm install && pnpm dev:web` (loads auth and service env from the environment or root `.env` via your shell)
6. **Worker** (new tab in `apps/api`): `uv run python -m pcc.worker.main`

Visit http://localhost:3000 — unauthenticated visitors are sent to `/signin`. After Google sign-in with the allowlisted account, the home page shows capture, Inbox, and **FastAPI: Connected**. API docs: http://localhost:8000/docs.

### Local API authentication (Milestone 3.2)

| Variable | Used by | Purpose |
|---|---|---|
| `PCC_SERVICE_CREDENTIAL` | FastAPI + Next.js (server-only) | Shared secret; send as `Authorization: Bearer <value>` |
| `PCC_SERVICE_CREDENTIAL_PREVIOUS` | FastAPI (optional) | Previous secret accepted during planned rotation |
| `API_INTERNAL_URL` | Next.js (server-only) | FastAPI base URL (default `http://localhost:8000`) |
| `TEST_DATABASE_URL` | Backend tests | Must target a database named `pcc_test` |

`GET /api/v1/health` stays unauthenticated. `GET /api/v1/captures` requires scope `captures:read`; `POST /api/v1/captures` requires `captures:write`. The service credential grants both.

### Website Google sign-in (Milestone 3.3)

Auth.js v5 (`next-auth` v5 beta) with `@auth/pg-adapter`, Google provider, and PostgreSQL database sessions. See `docs/google-signin-local.md` for Google Cloud callback URLs and the full checklist.

| Variable | Used by | Purpose |
|---|---|---|
| `AUTH_SECRET` | Next.js (server-only) | Auth.js session secret |
| `AUTH_GOOGLE_ID` / `AUTH_GOOGLE_SECRET` | Next.js (server-only) | Google OAuth Web client |
| `PCC_ALLOWED_GOOGLE_EMAILS` | Next.js (server-only) | Allowlist; missing/empty fails closed |
| `AUTH_DATABASE_URL` | Next.js (optional) | pg URL; otherwise `DATABASE_URL` is rewritten |

Local Google redirect URI: `http://localhost:3000/api/auth/callback/google`.

### Scoped API tokens (Milestone 3.4)

Allowlisted operators manage tokens at `/settings/api-tokens` after Google sign-in. FastAPI stores only SHA-256 hashes. Bearer tokens use the `pcc_at_` prefix and may carry `captures:read` and/or `captures:write`. Management routes (`/api/v1/api-tokens`) accept the Next.js service credential only; personal API tokens cannot create or revoke other tokens. The raw token is returned once at creation. ChatGPT integration is still Milestone 4.

### Test a background job

While the worker is running, in another tab:

```bash
cd apps/api
uv run python -m pcc.worker.submit_demo
```

Watch the worker terminal for the completed job.

### Run tests

```bash
cd apps/api
uv run pytest
uv run ruff check src tests
```

Backend database tests require `TEST_DATABASE_URL` pointing at a database named `pcc_test`; without it, those tests fail by design.

At the root: `pnpm lint:web && pnpm test:web && pnpm build:web`.

## What is and isn't included

Included: a Universal Capture web form (text or URL, with pending, success, and error feedback) and an Inbox listing saved captures; FastAPI endpoints `GET /api/v1/health`, `POST|GET /api/v1/captures`, and API-token create/list/revoke; FastAPI service-credential and hashed scoped API-token authentication (`captures:read` / `captures:write`); Auth.js v5 Google sign-in with a verified-email allowlist and PostgreSQL database sessions protecting pages and Server Actions; owner-only `/settings/api-tokens` UI; SQLAlchemy models and Alembic migrations (`captures`, Auth.js session tables, `api_tokens`, plus unused `projects` and `tasks` tables); PostgreSQL; Redis and an RQ worker with a demo job only; backend and frontend tests; CI; and ADRs. See `docs/ARCHITECTURE.md` for details.

Not yet included: file uploads, object storage, task and project APIs, URL remote fetching, capture processing, AI integrations, ChatGPT integration, ChatGPT history import, agents, PWA offline support, production Dockerfiles, TLS, backups, and full production hardening. **Do not expose this scaffold to the internet or upload private journal entries yet.**

## Architecture

- `apps/web`: Next.js UI
- `apps/api`: FastAPI HTTP server + separate worker process
- `packages/api-client`: reserved for OpenAPI-generated client
- `docs/decisions`: architectural decisions
- `compose.yaml`: local PostgreSQL and Redis only, loopback-bound ports

The database is the system of record; the worker is for slow tasks; the AI provider will be an adapter, not the owner of business state.

## Troubleshooting

- Docker port conflicts: check whether PostgreSQL/Redis are already running on 5432/6379.
- If the web page says API not reachable, confirm the API is running on port 8000.
- If migrations cannot connect, run `docker compose ps` and wait for PostgreSQL to become healthy.
- If pnpm is missing, install it via Corepack or Homebrew.
- If Python tooling fails, check `uv --version` and `python3 --version`.

## Next milestone

Continue Milestone 3 per ADR 0003: private HTTPS deployment (API tokens are implemented). See `docs/ROADMAP.md`.
