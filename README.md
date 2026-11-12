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
2. **Service credential**: set the same `PCC_SERVICE_CREDENTIAL` value for the API and Next.js processes (see `.env.example`). Capture create/list require it; do not use a `NEXT_PUBLIC_` prefix.
3. **Python dependencies and migrations**: `cd apps/api && uv sync --group dev && uv run alembic upgrade head`
4. **API** (same `apps/api` directory): `uv run uvicorn pcc.main:app --reload --host 127.0.0.1 --port 8000`
5. **Web** (repository root): `pnpm install && pnpm dev:web` (loads `PCC_SERVICE_CREDENTIAL` / `API_INTERNAL_URL` from the environment or root `.env` via your shell)
6. **Worker** (new tab in `apps/api`): `uv run python -m pcc.worker.main`

Visit http://localhost:3000 and http://localhost:8000/docs. The home page should show **FastAPI: Connected**.

### Local API authentication (Milestone 3.2)

| Variable | Used by | Purpose |
|---|---|---|
| `PCC_SERVICE_CREDENTIAL` | FastAPI + Next.js (server-only) | Shared secret; send as `Authorization: Bearer <value>` |
| `PCC_SERVICE_CREDENTIAL_PREVIOUS` | FastAPI (optional) | Previous secret accepted during planned rotation |
| `API_INTERNAL_URL` | Next.js (server-only) | FastAPI base URL (default `http://localhost:8000`) |
| `TEST_DATABASE_URL` | Backend tests | Must target a database named `pcc_test` |

`GET /api/v1/health` stays unauthenticated. `GET /api/v1/captures` requires scope `captures:read`; `POST /api/v1/captures` requires `captures:write`. The service credential grants both. Google sign-in, Auth.js, and personal API token issuance are not implemented yet (see ADR 0003).

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

Included: a Universal Capture web form (text or URL, with pending, success, and error feedback) and an Inbox listing saved captures; FastAPI endpoints `GET /api/v1/health`, `POST /api/v1/captures`, and `GET /api/v1/captures`; FastAPI service-credential authentication with scopes `captures:read` / `captures:write` on capture endpoints; SQLAlchemy models and Alembic migrations (`captures`, plus unused `projects` and `tasks` tables); PostgreSQL; Redis and an RQ worker with a demo job only; backend and frontend tests; CI; and ADRs. See `docs/ARCHITECTURE.md` for details.

Not yet included: website Google sign-in / Auth.js, personal API token issuance UI, file uploads, object storage, task and project APIs, URL remote fetching, capture processing, AI integrations, ChatGPT integration, ChatGPT history import, agents, PWA offline support, production Dockerfiles, TLS, backups, and full production hardening. **Do not expose this scaffold to the internet or upload private journal entries yet.**

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

Continue Milestone 3 per ADR 0003: website Google sign-in (Auth.js v5), protecting pages and Server Actions with sessions, then private deployment. See `docs/ROADMAP.md`.
