# Personal Command Center (PCC) — Architecture

**Last updated:** 2026-11-12 (reconciled with `ROADMAP.md` and `HANDOFF.md` after Universal Capture v1 was merged)
**Branch inspected:** `main` at `636c026` (Universal Capture v1, PR #1, merged)

## How to read this document

This file separates **what the repository actually contains** from **what is only planned**.

- **Part A (Verified implementation)** was derived by reading source, configuration, migrations, tests, CI, and Docker Compose in the repository. Unless noted, tests were **not** re-run for this document. See [Verification status](#verification-status) for what was and was not executed.
- **Part B (Planned architecture)** is taken from `docs/PROJECT.md`, `docs/ROADMAP.md`, `docs/HANDOFF.md`, and the ADRs. **None of it is implemented.**
- **Part C** lists discrepancies between documentation and code, and unresolved questions.

Product intent lives in `PROJECT.md`, sequencing in `ROADMAP.md`, and the next action in `HANDOFF.md`. This file describes technical reality.

---

# Part A — Verified implementation

## A1. System summary

PCC is currently a **single-user capture-and-Inbox application**. A user submits text or a URL string through a web form. It is stored in PostgreSQL and listed in an Inbox. That is the only implemented product capability.

- No authentication or authorization exists anywhere (UI or API).
- No AI/LLM integration exists.
- No code processes captures: they are stored as `pending` and never change status.
- A Redis/RQ worker exists as infrastructure with a demo job only.

The README states this is "a development foundation, not a production-ready app" and warns against exposing it to the internet. That warning is accurate.

## A2. Components and responsibilities

```
Browser ──HTML/RSC/Server Action──▶ Next.js (apps/web, :3000)
                                        │  server-side fetch (HTTP/JSON)
                                        ▼
                                  FastAPI (apps/api, :8000) ──SQLAlchemy/psycopg──▶ PostgreSQL 17
                                                                                      (Docker, :5432)
 RQ worker (apps/api, separate process) ──redis-py──▶ Redis 7 (Docker, :6379)
 (worker is NOT connected to the capture flow)
```

| Component | Location | Responsibility (as implemented) |
|---|---|---|
| Web UI | `apps/web` | Next.js 15 / React 19 App Router. Single page (`/`): capture form, Inbox list, FastAPI health indicator. |
| Server Action | `apps/web/app/actions.ts` | `createCapture` validates/trims input, POSTs JSON to FastAPI, returns a result state, and calls `revalidatePath("/")` on success. |
| Client form | `apps/web/app/capture-form.tsx` | `useActionState` form: pending ("Saving…"), success message with reset, error message with input preserved. |
| API | `apps/api/src/pcc/main.py`, `api/captures.py` | FastAPI app exposing health and capture endpoints. |
| Services | `apps/api/src/pcc/services/captures.py` | `create_capture` and `list_captures` against a SQLAlchemy `Session`. |
| Schemas | `apps/api/src/pcc/schemas/capture.py` | Pydantic request/response models and validation. |
| Persistence | `apps/api/src/pcc/db/` | SQLAlchemy 2.0 declarative models, engine, `SessionLocal`. |
| Migrations | `apps/api/migrations/` | Alembic revisions. |
| Worker | `apps/api/src/pcc/worker/` | RQ `Worker` on queue `default`; one `sample_job`; `submit_demo` enqueues it. |
| Infrastructure | `compose.yaml` | PostgreSQL and Redis only, loopback-bound. |

### Request flows (verified from code)

**Create capture**
1. User submits the form in `capture-form.tsx` (client component, `useActionState`).
2. `createCapture(prevState, formData)` runs on the Next.js server. It reads `source_type`, `title`, `content` and trims title and content (the API trims again; see Validation limits).
3. Empty content returns an error state without calling the API. Otherwise it `POST`s `{source_type, title|null, content}` to `${API_INTERNAL_URL ?? "http://localhost:8000"}/api/v1/captures`.
4. FastAPI is the authority on validation: `CaptureCreate` trims and validates the body (422 on failure), then `create_capture` inserts a `Capture` row (status `pending`) and returns 201 with `CaptureRead`.
5. A 422 is mapped to field-level errors (`title` / `content`) shown under the matching form field; other non-OK responses, malformed bodies, and thrown network errors return a generic error state. In every error case the user's raw input (including the selected type) is echoed back. Success returns empty values and calls `revalidatePath("/")`.

**Load Inbox**
1. `page.tsx` is a server component. It calls `GET /api/v1/health` and `GET /api/v1/captures` in parallel with `cache: "no-store"`. The captures call sends no `limit`, so the API default of 50 applies.
2. A failure of either request yields `null`, and the UI shows "Unable to load captures" / "Not reachable".

The browser never talks to FastAPI directly. All API calls originate from the Next.js server. This is why CORS is not currently needed.

## A3. API surface (verified)

| Method & path | Behavior |
|---|---|
| `GET /api/v1/health` | Returns `{"status": "ok", "service": "pcc-api"}`. Does **not** check database or Redis. |
| `POST /api/v1/captures` | Body: `source_type` (`"text"` or `"url"`), `title` (optional, max 300), `content` (trimmed; must not be blank). For `url` captures `content` must be an absolute `http`/`https` URL, at most 2,048 characters. For `text` captures it is at most 100,000 characters. Returns 201 and the capture. Invalid input returns 422 with errors on `body.title` / `body.content`. |
| `GET /api/v1/captures` | Query `limit` (1–100, default 50). Returns captures ordered by `created_at` desc, then `id` desc. |

FastAPI also serves its automatic OpenAPI docs (`/docs`, `/openapi.json`) because no override exists.

**Not implemented:** get-by-id, update, delete, search, pagination beyond `limit`, task or project endpoints, any auth.

**Validation rules (`schemas/capture.py`, enforced by FastAPI):**
- `title` and `content` have leading/trailing whitespace trimmed; internal whitespace and line breaks are preserved. A blank title becomes `null`; blank content is rejected. Title max is 300 characters.
- `url` captures must be absolute `http` or `https` URLs with a valid hostname (domain, IP literal, or `localhost`), no whitespace or control characters, no embedded username or password, and at most 2,048 characters. The trimmed original string is stored; it is not normalized (no case, trailing-slash, or encoding changes).
- `text` captures are never URL-checked and are limited to 100,000 characters.
- There is no fetching of remote content.
- The Next.js Server Action also trims, but it does not duplicate these rules.

## A4. Data model (verified from `db/models.py` and migrations)

Three tables exist, created by two Alembic revisions (`0001_initial` then `09d577e3aed4`).

**`captures`** (the only table used by any code path)

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | `uuid.uuid4` default (app-side) |
| `source_type` | varchar(32), not null | CHECK in (`text`, `url`) |
| `title` | varchar(300), nullable | |
| `content` | text, not null | |
| `status` | varchar(32), not null | default `pending`; CHECK in (`pending`, `processing`, `processed`, `failed`) |
| `created_at` | timestamptz, not null | server default `CURRENT_TIMESTAMP` |
| `updated_at` | timestamptz, not null | server default; ORM `onupdate` |

Only `pending` is ever written. `processing`, `processed` and `failed` are permitted by the constraint but no code sets them.

**`projects`** (`id`, `name`, `description`, `created_at`) and **`tasks`** (`id`, `project_id` FK, `title`, `status`, `created_at`) exist as models and tables from the scaffold migration. **No API, service, schema, UI, or test uses them.**

**Not present:** tables for conversations, messages, knowledge, threads/workstreams, agents, runs, integrations, users, or sessions.

## A5. Backend structure and conventions

```
apps/api/
  pyproject.toml          # Python >=3.12; fastapi, sqlalchemy 2, psycopg 3, alembic, redis, rq, pydantic-settings
  alembic.ini
  migrations/             # env.py reads DATABASE_URL via pcc.core.config (overrides alembic.ini URL)
  src/pcc/
    main.py               # FastAPI app, health route, includes captures router
    api/captures.py       # routes + get_db dependency
    schemas/capture.py    # Pydantic models
    services/captures.py  # business/data logic
    db/{base,models,session}.py
    core/config.py        # pydantic-settings: database_url, redis_url (reads .env in cwd)
    worker/{main,jobs,submit_demo}.py
  tests/                  # conftest.py, test_captures.py, test_health.py
```

The layering is route → service → SQLAlchemy model, with Pydantic schemas at the boundary. Sessions are created per request by `get_db`. Services call `commit()` themselves.

## A6. Frontend structure

```
apps/web/
  package.json            # next ^15.3, react ^19, vitest ^3.1, typescript ^5.8
  tsconfig.json
  app/
    layout.tsx            # root layout, metadata, imports styles.css
    page.tsx              # server component: health + Inbox + <CaptureForm/>
    capture-form.tsx      # "use client" form (useActionState)
    capture-state.ts      # CaptureFormState type + initialCaptureState
    actions.ts            # "use server" createCapture
    actions.test.ts       # 27 Vitest tests of createCapture
    styles.css            # global CSS (no CSS framework)
```

State types live in `capture-state.ts` because a `"use server"` module may only export async functions. `Capture` and `Health` types in `page.tsx` are hand-written, not generated.

## A7. Infrastructure and configuration

**`compose.yaml`** defines `postgres:17-alpine` (volume `postgres_data`, healthcheck) and `redis:7-alpine` (healthcheck, no volume). Both bind to `127.0.0.1`. The API, web app and worker are **not** containerized, and there are no Dockerfiles. The only database created is `pcc`.

**Environment variables**

| Variable | Used by code? | Notes |
|---|---|---|
| `DATABASE_URL` | Yes (`core/config.py`, Alembic) | |
| `REDIS_URL` | Yes (worker) | |
| `POSTGRES_USER/PASSWORD/DB` | Yes (Compose) | Defaults in `compose.yaml` |
| `API_INTERNAL_URL` | Yes (`actions.ts`, `page.tsx`) | Defaults to `http://localhost:8000`. **Not listed in `.env.example`.** |
| `TEST_DATABASE_URL` | Yes (`tests/conftest.py`) | Must point at a database named `pcc_test`. **Not listed in `.env.example`.** |
| `API_CORS_ORIGINS` | **No** | In `.env.example`; no CORS middleware exists. |
| `NEXT_PUBLIC_API_BASE_URL` | **No** | In `.env.example`; not referenced by web code. |

Secrets: only a local development password default exists. `.env` files are gitignored.

## A8. Development and test commands

Prerequisites per README: Docker, Node 22, pnpm 10.11.0, Python 3.12+, `uv`.

| Task | Command | Directory |
|---|---|---|
| Start Postgres + Redis | `docker compose up -d` (or `make infra-up`) | repo root |
| Install Python deps | `uv sync --group dev` | `apps/api` |
| Migrate | `uv run alembic upgrade head` (or `make migrate`) | `apps/api` |
| Run API | `uv run uvicorn pcc.main:app --reload --host 127.0.0.1 --port 8000` (or `make api`) | `apps/api` |
| Run worker | `uv run python -m pcc.worker.main` (or `make worker`) | `apps/api` |
| Enqueue demo job | `uv run python -m pcc.worker.submit_demo` | `apps/api` |
| Install JS deps | `pnpm install` | repo root |
| Run web | `pnpm dev:web` (or `make web`) | repo root |
| Frontend typecheck ("lint") | `pnpm lint:web` (runs `tsc --noEmit`) | repo root |
| Frontend tests | `pnpm test:web` (runs `vitest run`) | repo root |
| Frontend build | `pnpm build:web` | repo root |
| Backend tests | `TEST_DATABASE_URL=<url to pcc_test> uv run pytest` | `apps/api` |
| Backend lint | `uv run ruff check src tests` | `apps/api` |

**Backend test design:** all API endpoint tests in `test_captures.py` and `test_capture_validation.py` run through the `db_client` fixture. It refuses to run unless `TEST_DATABASE_URL` is set and the database name is exactly `pcc_test`. An autouse override blocks unisolated `get_db` usage so tests cannot accidentally hit development/production databases. The fixture runs `Base.metadata.create_all` and `drop_all` around each test and overrides `get_db`. The tests therefore build schema from the models and **do not exercise the Alembic migrations**. CI provisions `pcc_test` through a Postgres service container; locally it must be created manually.

**Frontend test design:** only the Server Action is tested (success and reset, 422 field-error mapping, generic fallbacks for malformed bodies, 5xx and network failures, blank content, and the `source_type` returned to the form). `fetch` and `next/cache` are mocked in Vitest's default Node environment. There are no component tests, browser tests, or Vitest config file.

**CI (`.github/workflows/ci.yml`)** runs on every push and PR:
- Backend job: `uv sync`, `uv run pytest`, `uv run ruff check`.
- Frontend job: `pnpm install --no-frozen-lockfile`, `pnpm lint:web`, `pnpm test:web`, `pnpm build:web`.
- See Part C for remaining gaps (for example migration coverage and local `pcc_test` setup).

## A9. Verified architectural decisions

| Decision | Status in code |
|---|---|
| **ADR 0001:** Monorepo, modular monolith; HTTP API and worker from the same Python package | Implemented. `apps/web` + `apps/api`; the worker is in the `pcc.worker` package. |
| **ADR 0002:** PostgreSQL for structured state; file originals outside DB behind a storage abstraction | PostgreSQL is implemented. **File storage is not**: no abstraction, uploads, or upload directory (the `.gitignore` lists `uploads/` only). Status is "Proposed". |
| Web calls the API server-side only | Implemented (Server Action and server component). |
| Keep the existing Server Action + FastAPI architecture for capture UX | Implemented and merged to `main` (PR #1). |
| `packages/api-client` reserved for OpenAPI-generated client | **Placeholder only** (a README). The web app hand-writes its types. |
| Tests protect real data via `pcc_test` guard | Implemented in `conftest.py`. |

## A10. Verification status

| Item | Status |
|---|---|
| Source, config, migrations, tests, CI and Compose were read for this document | Done (original review 2026-11-09; capture sections updated 2026-11-12) |
| Frontend `pnpm lint:web`, `pnpm test:web` (27 Server Action tests), `pnpm build:web` | Passed locally and in GitHub Actions on PR #1 |
| Backend `uv run pytest` (61 tests, using `pcc_test` Postgres) and `ruff check src tests` | Passed locally and in GitHub Actions on PR #1 (CI provisions Postgres 17 as a service container) |
| Alembic migrations, Docker Compose services | **Still not exercised by any test.** Migrations were applied by hand to a local dev database during browser testing only. |
| Browser acceptance of the capture form | **Performed 2026-11-12** in real Chrome against the full stack (invalid URL field error, correction without reselecting Type, text capture, backend-down generic error with input kept, success reset). Evidence is in the Project store `media/`. The "Saving…" pending state and whitespace-only submit were not observed in the browser. |
| Uncommitted state | None. Capture work and the docs are committed; Universal Capture v1 is merged to `main`. |

---

# Part B — Planned architecture (NOT implemented)

Everything below comes from `PROJECT.md`, `ROADMAP.md`, `HANDOFF.md` and ADR 0002. There is no corresponding code. Treat it as intent that may change.

## B1. Authentication, API security, and minimal private deployment (Roadmap M3)
Planned: single-user auth protecting both UI and API, secure secrets, HTTPS, persistent Postgres with backups, and health checks, in a minimal private deployment designed so remote access can be added later (Roadmap M3 combines the former M3 and M4). **Milestone 3.1 architecture planning is complete**; implementation follows `docs/decisions/0003-m3-auth-security-design.md`. A small VPS with Docker Compose remains a hosting candidate, not a final decision. **Today:** no auth, no production configuration, no Dockerfiles, and a health endpoint that checks nothing downstream.

Architecture decision status (accepted design, not implemented): ADR 0003 selects Google sign-in with an explicit verified-email allowlist, Auth.js v5 with PostgreSQL database sessions (`@auth/*` Postgres-compatible adapter), protection of pages and Server Actions, FastAPI-enforced API authorization with initial scopes `captures:read` / `captures:write`, a server-side Next.js→FastAPI service credential with rotation/compromise procedure, scoped revocable API tokens (first token issued only via authenticated allowlisted control path), and a private HTTPS-first deployment baseline. ChatGPT iPhone feasibility remains a Milestone 4 gate, not a Milestone 3 completion requirement.

## B2. ChatGPT ↔ PCC integration (Roadmap M4)
Planned: let the standard ChatGPT app (including iPhone) save and retrieve PCC data through a supported, authenticated tool/MCP-style interface.
- **Feasibility is unverified.** The roadmap makes it an explicit gate: confirm the supported mechanism, iPhone availability, authentication requirements, and network accessibility before building. The first goal is a capture created from the standard ChatGPT iPhone app that appears in the Inbox. It depends on Milestone 3.
- **No code exists:** no MCP server, tool endpoints, OAuth, or ChatGPT-specific adapter.
- PCC calling an AI provider's API is a different direction and is also not implemented.

## B3. Historical ChatGPT conversation ingestion (Roadmap M6)
Planned: import a ChatGPT data export, preserve conversations with timestamps and provenance, make imports idempotent, and derive reviewable decisions, tasks and knowledge.
- **No code exists:** no importer, no conversation/message tables, no parser, and no sample export has been inspected in the repo.
- Export formats and contents are an open question in `PROJECT.md`. Do not assume the export includes memory or all history.

## B4. Background processing, AI providers, and agents (Roadmap M7)
Planned: Redis/RQ processing of captures, an AI-provider abstraction with budgets and logging, and **agent, thread/workstream, and run** records with a dashboard (status, outputs, errors, approvals).
- **Implemented today:** only the generic RQ worker skeleton and `sample_job`.
- **Not implemented:** capture-processing jobs, enqueueing from the API, provider abstraction, agents, threads, runs, approvals, dashboards, or any LLM call. `PROJECT.md` itself says these are requirements, not existing models.

## B5. Other planned items
- Task, project, and knowledge capabilities (Roadmap M5): knowledge search/retrieval, projects, tasks UI/API; briefings.
- File upload and a storage abstraction (ADR 0002, Proposed).
- A generated TypeScript API client (`packages/api-client`).

---

# Part C — Discrepancies and unresolved questions

## C1. Documentation vs. code

| # | Document says | Code shows |
|---|---|---|
| 1 | `HANDOFF.md`: API route `GET /health` | **Resolved 2026-11-09:** `HANDOFF.md` and `ROADMAP.md` now say `GET /api/v1/health`, matching `main.py`. |
| 2 | `HANDOFF.md`: capture model "UUID ID, source_type, optional title, content, status, timestamps" | Correct, but the response also includes `updated_at`. Minor, not a conflict. |
| 3 | `README.md` "Included" and "Next milestone" sections described only the scaffold | **Resolved 2026-11-09:** README updated to describe captures, the Inbox, current endpoints, and the actual next milestone. |
| 4 | `README.md`: "Open **four** Terminal tabs" | **Resolved 2026-11-09:** wording changed to "several" tabs. |
| 5 | `ADR 0001`: "Organize backend code by business capability" | Backend is organized **by layer** (`api/`, `schemas/`, `services/`, `db/`). With one domain this is fine, but it differs from the stated intent. |
| 6 | `ADR 0002`: storage abstraction and local-disk uploads | Not implemented (ADR is "Proposed"). `README.md` correctly lists uploads as not included. |
| 7 | `.env.example` documents `API_CORS_ORIGINS` and `NEXT_PUBLIC_API_BASE_URL` | Neither is read by any code. The code uses `API_INTERNAL_URL` and `TEST_DATABASE_URL`, which `.env.example` omits. |
| 8 | `PROJECT.md` §6 listed the capture form as reported/not inspected | **Resolved 2026-11-12:** `PROJECT.md` §6 updated; the form passed browser acceptance and is merged. |
| 9 | `ROADMAP.md` M1: "Address generated `tsconfig.tsbuildinfo` ignore rule" | **Resolved:** `.gitignore` contains `*.tsbuildinfo`, and `ROADMAP.md` M1 marks it done. |
| 10 | `PROJECT.md` says agent/thread/run models are future requirements | Correct. However, `projects` and `tasks` tables **do** exist (migration `0001_initial`) with no API or UI. No doc describes this. |
| 11 | `docs/PROJECT.md` and `docs/ROADMAP.md` are presented as living specs | **Resolved:** both are tracked in Git on `main`. |

## C2. Likely problems found in configuration (not run, inferred from files)

1. **CI backend job failed (resolved).** `ci.yml` had no PostgreSQL service and no `TEST_DATABASE_URL`, so the `db_client` tests errored in CI (confirmed on PR #1). `ci.yml` now starts a `postgres:17-alpine` service that creates `pcc_test` and sets `TEST_DATABASE_URL`; backend CI passes.
2. **CI skipped frontend tests (resolved).** The frontend job now runs `test:web` between `lint:web` and `build:web`.
3. **`make test` fails without `TEST_DATABASE_URL`** for the same reason as (1).
4. **Local `pcc_test` is still not created by repo tooling.** Compose creates only `pcc`, so developers must create `pcc_test` manually (CI creates it through its service container).
5. **Migrations are untested.** Tests use `create_all`, so a migration/model mismatch would not be caught.
6. **Health check is shallow.** It reports `ok` without verifying PostgreSQL or Redis.
7. **Capture status never leaves `pending`**, and capture creation does not enqueue any job. The Inbox's "status" is therefore always `pending`.
8. **Whitespace handling (resolved).** The API now trims title and content, so direct API clients cannot store padded values; the Server Action trims as well.
9. **Frontend-only note:** the form is not usable without JavaScript, because it depends on `useActionState` in a client component.

## C3. Unresolved questions

- Does the standard ChatGPT app (especially on iPhone) support a custom tool/MCP integration for this account, and with what authentication? (Roadmap M4 feasibility gate; `PROJECT.md` open question.)
- What ChatGPT export format and metadata will actually be importable, and does it include memory? No real export has been inspected.
- ~~Should URL captures be fetched or enriched, and what schemes are accepted?~~ **Answered in Roadmap M2:** only absolute `http`/`https` URLs are accepted and stored as the trimmed original string; remote content is not fetched. If server-side fetching is ever added, it needs SSRF controls (accepted URLs may point at localhost or private hosts).
- ~~Which authentication approach fits a single-user deployment, and how will the Next.js server authenticate to FastAPI?~~ **Answered in ADR 0003:** Google sign-in with a verified-email allowlist, Auth.js v5 database sessions in PostgreSQL, protection of pages and Server Actions, a server-side service credential for Next.js→FastAPI, and scoped/revocable API tokens (`captures:read`, `captures:write`) for non-browser clients.
- ~~How should backend CI obtain a Postgres `pcc_test` database?~~ **Answered:** a GitHub Actions Postgres service container.
- What is the intended lifecycle of capture status values (`processing`, `processed`, `failed`), and which component owns the transitions?
- Should `projects` and `tasks` be kept, reshaped, or removed given that nothing uses them yet?
- Does the backend need a CORS policy, or should `API_CORS_ORIGINS` / `NEXT_PUBLIC_API_BASE_URL` be removed from `.env.example`?
- Is the known `.pth` "hidden flag" import issue (see `HANDOFF.md`) still occurring? Its root cause is unestablished and not investigated here. `pyproject.toml` includes `pythonpath = ["src"]` for pytest.

## C4. Maintenance

Update this document whenever the implemented architecture changes. Move an item from Part B to Part A only after the code exists and has been verified. Do not describe planned integrations, ingestion, or agents as implemented.
