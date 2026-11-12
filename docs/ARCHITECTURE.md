# Personal Command Center (PCC) — Architecture

**Last updated:** 2026-11-12 (Milestone 3.3 Google/Auth.js website sessions)
**Branch inspected:** `feature/m3-google-auth` (Milestone 3.3); `main` includes through Milestone 3.2 (`35fc6e3`)

## How to read this document

This file separates **what the repository actually contains** from **what is only planned**.

- **Part A (Verified implementation)** was derived by reading source, configuration, migrations, tests, CI, and Docker Compose in the repository. Unless noted, tests were **not** re-run for this document. See [Verification status](#verification-status) for what was and was not executed.
- **Part B (Planned architecture)** is taken from `docs/PROJECT.md`, `docs/ROADMAP.md`, `docs/HANDOFF.md`, and the ADRs. Items move to Part A when verified in code; Part B may note partial delivery (for example Milestone 3.2).
- **Part C** lists discrepancies between documentation and code, and unresolved questions.

Product intent lives in `PROJECT.md`, sequencing in `ROADMAP.md`, and the next action in `HANDOFF.md`. This file describes technical reality.

---

# Part A — Verified implementation

## A1. System summary

PCC is currently a **single-user capture-and-Inbox application**. A user signs in with an allowlisted Google account, then submits text or a URL string through a web form. It is stored in PostgreSQL and listed in an Inbox. That is the only implemented product capability.

- Website auth: Auth.js v5 Google sign-in with a verified-email allowlist and PostgreSQL database sessions. Pages and Server Actions check the session server-side; sign-out deletes the session row.
- FastAPI capture endpoints require a server-to-server service credential (`PCC_SERVICE_CREDENTIAL`) with scopes `captures:read` / `captures:write`.
- No AI/LLM integration exists.
- No code processes captures: they are stored as `pending` and never change status.
- A Redis/RQ worker exists as infrastructure with a demo job only.

The README states this is "a development foundation, not a production-ready app" and warns against exposing it to the internet. That warning remains accurate until private HTTPS deployment.

## A2. Components and responsibilities

```
Browser ──HTML/RSC/Server Action──▶ Next.js (apps/web, :3000)
   │ Auth.js session cookie (opaque)         │  auth() + allowlist check
   │                                         │  server-side fetch + Bearer service credential
   └──── /api/auth/* (Auth.js) ──────────────┤
                                             ▼
                                       FastAPI (apps/api, :8000) ──SQLAlchemy/psycopg──▶ PostgreSQL
 RQ worker (apps/api) ──redis-py──▶ Redis 7                                              │
 (not connected to capture)              Auth.js tables (users/accounts/sessions/…) ─────┘
```

| Component | Location | Responsibility (as implemented) |
|---|---|---|
| Web UI | `apps/web` | Next.js 15 / React 19 App Router. `/` (protected): capture form, Inbox, health, sign-out. `/signin`: Google sign-in. |
| Auth.js | `apps/web/auth.ts`, `auth-allowlist.ts`, `auth-session.ts`, `app/api/auth/[...nextauth]` | Google provider, `@auth/pg-adapter` database sessions, allowlist, handlers. |
| Server Action | `apps/web/app/actions.ts` | `createCapture` requires allowlisted session, then validates/trims, POSTs to FastAPI with service credential. |
| Client form | `apps/web/app/capture-form.tsx` | `useActionState` form: pending ("Saving…"), success message with reset, error message with input preserved. |
| API | `apps/api/src/pcc/main.py`, `api/captures.py` | FastAPI app exposing health and capture endpoints. |
| API auth | `apps/api/src/pcc/auth/` | Bearer service-credential verification and `require_scopes`. |
| Services | `apps/api/src/pcc/services/captures.py` | `create_capture` and `list_captures` against a SQLAlchemy `Session`. |
| Schemas | `apps/api/src/pcc/schemas/capture.py` | Pydantic request/response models and validation. |
| Persistence | `apps/api/src/pcc/db/` | SQLAlchemy 2.0 declarative models, engine, `SessionLocal`. |
| Migrations | `apps/api/migrations/` | Alembic revisions (including Auth.js tables). |
| Worker | `apps/api/src/pcc/worker/` | RQ `Worker` on queue `default`; one `sample_job`; `submit_demo` enqueues it. |
| Infrastructure | `compose.yaml` | PostgreSQL and Redis only, loopback-bound. |

### Request flows (verified from code)

**Create capture**
1. User submits the form in `capture-form.tsx` (client component, `useActionState`).
2. `createCapture(prevState, formData)` runs on the Next.js server. It requires an allowlisted Auth.js session; otherwise it returns an error and does **not** call FastAPI.
3. It reads `source_type`, `title`, `content` and trims title and content (the API trims again; see Validation limits).
4. Empty content returns an error state without calling the API. Otherwise it `POST`s `{source_type, title|null, content}` to `${API_INTERNAL_URL ?? "http://localhost:8000"}/api/v1/captures` with `Authorization: Bearer ${PCC_SERVICE_CREDENTIAL}` (server-only; never sent to the browser).
5. FastAPI authenticates the service credential, requires `captures:write`, then validates: `CaptureCreate` trims and validates the body (422 on failure), then `create_capture` inserts a `Capture` row (status `pending`) and returns 201 with `CaptureRead`.
6. A 422 is mapped to field-level errors (`title` / `content`) shown under the matching form field; other non-OK responses, malformed bodies, and thrown network errors return a generic error state. In every error case the user's raw input (including the selected type) is echoed back. Success returns empty values and calls `revalidatePath("/")`.

**Load Inbox**
1. `page.tsx` is a server component. It requires an allowlisted Auth.js session (`getAllowlistedSession`); otherwise it redirects to `/signin`.
2. It calls `GET /api/v1/health` (unauthenticated) and `GET /api/v1/captures` (Bearer service credential, `captures:read`) in parallel with `cache: "no-store"`. The captures call sends no `limit`, so the API default of 50 applies.
3. A failure of either request yields `null`, and the UI shows "Unable to load captures" / "Not reachable".

**Sign-in / sign-out**
1. `/signin` starts Google OAuth via Auth.js. The `signIn` callback requires Google `email_verified === true` and a case-insensitive match against `PCC_ALLOWED_GOOGLE_EMAILS` (fail closed if missing).
2. Successful sign-in creates a row in `sessions` and sets an HTTP-only cookie with the opaque session token.
3. Sign-out calls Auth.js `signOut`, which deletes the `sessions` row and clears the cookie.

The browser never talks to FastAPI directly. All API calls originate from the Next.js server. The service credential must not use a `NEXT_PUBLIC_` prefix. This is why CORS is not currently needed.

## A3. API surface (verified)

| Method & path | Behavior |
|---|---|
| `GET /api/v1/health` | Unauthenticated. Returns `{"status": "ok", "service": "pcc-api"}`. Does **not** check database or Redis. |
| `POST /api/v1/captures` | Requires Bearer auth with scope `captures:write`. Body: `source_type` (`"text"` or `"url"`), `title` (optional, max 300), `content` (trimmed; must not be blank). For `url` captures `content` must be an absolute `http`/`https` URL, at most 2,048 characters. For `text` captures it is at most 100,000 characters. Returns 201 and the capture. Missing/invalid credentials → 401; insufficient scope → 403; invalid input → 422 with errors on `body.title` / `body.content`. |
| `GET /api/v1/captures` | Requires Bearer auth with scope `captures:read`. Query `limit` (1–100, default 50). Returns captures ordered by `created_at` desc, then `id` desc. |

FastAPI also serves its automatic OpenAPI docs (`/docs`, `/openapi.json`) because no override exists. Calling protected endpoints from `/docs` requires a Bearer token.

**Auth (Milestone 3.2 + 3.3):** FastAPI `pcc.auth` verifies `Authorization: Bearer` against `PCC_SERVICE_CREDENTIAL` (and optional `PCC_SERVICE_CREDENTIAL_PREVIOUS` for rotation). The service principal receives both capture scopes. Website Auth.js v5 Google sign-in with PostgreSQL database sessions and a verified-email allowlist protects pages and Server Actions. `require_scopes(...)` remains the reusable API authorization dependency for future personal API tokens.

**Not implemented:** get-by-id, update, delete, search, pagination beyond `limit`, task or project endpoints, personal API token CRUD.

**Validation rules (`schemas/capture.py`, enforced by FastAPI):**
- `title` and `content` have leading/trailing whitespace trimmed; internal whitespace and line breaks are preserved. A blank title becomes `null`; blank content is rejected. Title max is 300 characters.
- `url` captures must be absolute `http` or `https` URLs with a valid hostname (domain, IP literal, or `localhost`), no whitespace or control characters, no embedded username or password, and at most 2,048 characters. The trimmed original string is stored; it is not normalized (no case, trailing-slash, or encoding changes).
- `text` captures are never URL-checked and are limited to 100,000 characters.
- There is no fetching of remote content.
- The Next.js Server Action also trims, but it does not duplicate these rules.

## A4. Data model (verified from `db/models.py` and migrations)

Application and Auth.js tables exist, created by Alembic revisions `0001_initial`, `09d577e3aed4` (captures), and `0003_authjs_tables` (Auth.js).

**`captures`** (product data; Auth.js uses separate session tables below)

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

**Auth.js tables** (`users`, `accounts`, `sessions`, `verification_token`): owned by Alembic `0003_authjs_tables` to match `@auth/pg-adapter`. No SQLAlchemy models; the Next.js adapter talks to PostgreSQL via `pg`. `sessions.sessionToken` is unique; deleting a session row revokes that browser session.

**Not present:** tables for conversations, messages, knowledge, threads/workstreams, agents, runs, or integration API tokens.

## A5. Backend structure and conventions

```
apps/api/
  pyproject.toml          # Python >=3.12; fastapi, sqlalchemy 2, psycopg 3, alembic, redis, rq, pydantic-settings
  alembic.ini
  migrations/             # env.py reads DATABASE_URL via pcc.core.config (overrides alembic.ini URL)
  src/pcc/
    main.py               # FastAPI app, health route, includes captures router
    api/captures.py       # routes + get_db + require_scopes
    auth/                 # principals, credential verification, require_scopes
    schemas/capture.py    # Pydantic models
    services/captures.py  # business/data logic
    db/{base,models,session}.py
    core/config.py        # pydantic-settings: database_url, redis_url, service credential
    worker/{main,jobs,submit_demo}.py
  tests/                  # conftest.py, test_captures.py, test_capture_validation.py, test_auth.py, test_health.py
```

The layering is route → service → SQLAlchemy model, with Pydantic schemas at the boundary. Sessions are created per request by `get_db`. Services call `commit()` themselves.

## A6. Frontend structure

```
apps/web/
  package.json            # next ^15.3, react ^19, next-auth@5 beta, @auth/pg-adapter, pg, vitest
  auth.ts                 # NextAuth config (Google + PostgresAdapter, database sessions)
  auth-allowlist.ts       # PCC_ALLOWED_GOOGLE_EMAILS parsing / Google sign-in gate
  auth-session.ts         # getAllowlistedSession for pages and Server Actions
  auth-db.ts              # pg Pool + DATABASE_URL rewriting
  app/
    layout.tsx            # root layout, metadata, imports styles.css
    page.tsx              # protected: health + Inbox + <CaptureForm/> + sign-out
    signin/page.tsx       # Google sign-in
    api/auth/[...nextauth]/route.ts
    api.ts                # server-only API base URL + Bearer credential headers
    capture-form.tsx      # "use client" form (useActionState)
    capture-state.ts      # CaptureFormState type + initialCaptureState
    actions.ts            # "use server" createCapture (session-gated)
    auth-actions.ts       # signOutAction
    styles.css            # global CSS (no CSS framework)
```

State types live in `capture-state.ts` because a `"use server"` module may only export async functions. `Capture` and `Health` types in `page.tsx` are hand-written, not generated. Authorization is enforced in page/Server Action code on the Node runtime; Edge middleware is not used for session checks.

## A7. Infrastructure and configuration

**`compose.yaml`** defines `postgres:17-alpine` (volume `postgres_data`, healthcheck) and `redis:7-alpine` (healthcheck, no volume). Both bind to `127.0.0.1`. The API, web app and worker are **not** containerized, and there are no Dockerfiles. The only database created is `pcc`.

**Environment variables**

| Variable | Used by code? | Notes |
|---|---|---|
| `DATABASE_URL` | Yes (`core/config.py`, Alembic; Auth.js via rewrite) | |
| `AUTH_DATABASE_URL` | Yes (optional; Next.js `auth-db.ts`) | Preferred pg URL for Auth.js when set. |
| `REDIS_URL` | Yes (worker) | |
| `POSTGRES_USER/PASSWORD/DB` | Yes (Compose) | Defaults in `compose.yaml` |
| `PCC_SERVICE_CREDENTIAL` | Yes (FastAPI `core/config.py`; Next.js `app/api.ts`) | Server-only shared secret for capture endpoints. |
| `PCC_SERVICE_CREDENTIAL_PREVIOUS` | Yes (FastAPI) | Optional dual-read during rotation. |
| `API_INTERNAL_URL` | Yes (`app/api.ts`) | Defaults to `http://localhost:8000`. |
| `AUTH_SECRET` | Yes (Auth.js) | Session signing/encryption secret. |
| `AUTH_GOOGLE_ID` / `AUTH_GOOGLE_SECRET` | Yes (Auth.js Google provider) | OAuth Web client credentials. |
| `PCC_ALLOWED_GOOGLE_EMAILS` | Yes (`auth-allowlist.ts`) | Comma-separated; missing/empty fails closed. |
| `TEST_DATABASE_URL` | Yes (`tests/conftest.py`) | Must point at a database named `pcc_test`. |
| `API_CORS_ORIGINS` | **No** | Commented in `.env.example`; no CORS middleware exists. |
| `NEXT_PUBLIC_API_BASE_URL` | **No** | Commented in `.env.example`; not referenced by web code. |

Secrets stay server-only (never `NEXT_PUBLIC_`). `.env` files are gitignored. Local Google setup: `docs/google-signin-local.md`.

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

**Frontend test design:** Server Action tests (including session-gate denial and service-credential headers), plus unit tests for allowlist parsing, Auth.js session gating, sign-out action, and database URL rewriting. `fetch`, `next/cache`, and Auth.js session helpers are mocked in Vitest's Node environment. There are no component tests, browser tests, or Vitest config file. Live Google OAuth is not automated.

**CI (`.github/workflows/ci.yml`)** runs on every push and PR:
- Backend job: `uv sync`, `uv run pytest`, `uv run ruff check`.
- Frontend job: `pnpm install --no-frozen-lockfile`, `pnpm lint:web`, `pnpm test:web`, `pnpm build:web` (placeholder Auth.js env vars for build only).
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
| **ADR 0003** Google/Auth.js database sessions + FastAPI service credential | Milestone 3.2 + 3.3 implemented in code; API tokens and private deploy remain. |

## A10. Verification status

| Item | Status |
|---|---|
| Source, config, migrations, tests, CI and Compose were read for this document | Done (updated for M3.3 on 2026-11-12) |
| Frontend `pnpm lint:web`, `pnpm test:web` (50 tests), `pnpm build:web` | Passed locally for Milestone 3.3 |
| Backend `uv run pytest` (75 tests, `pcc_test`) and `ruff check src tests` | Passed locally for Milestone 3.3 |
| Alembic `0003_authjs_tables` | Applied manually to local Postgres (`alembic upgrade head`); not covered by automated tests |
| Browser acceptance of the capture form | **Performed 2026-11-12** (pre-auth). M3.3 Google OAuth browser acceptance still required (see `docs/google-signin-local.md`) |
| Client bundle secret leakage check | No `AUTH_*` / service credential values found under `.next/static` after production build |

---

# Part B — Planned architecture

Everything below comes from `PROJECT.md`, `ROADMAP.md`, `HANDOFF.md`, and the ADRs unless a subsection notes partial delivery already reflected in Part A. Treat unmarked items as intent that may change.

## B1. Authentication, API security, and minimal private deployment (Roadmap M3)
**Partial delivery:** Milestone 3.1 (ADR 0003) is accepted. **Milestone 3.2** (FastAPI service credential + scopes) and **Milestone 3.3** (Auth.js Google sign-in, PostgreSQL database sessions, page/Server Action protection) are implemented in Part A. Health remains unauthenticated at the API. Real Google OAuth browser acceptance for 3.3 may still be pending after merge.

**Still planned (not implemented):** external/personal API token issuance, storage (hashed), and revocation UI; production configuration, Dockerfiles, HTTPS private deployment, backups, and deep health checks. A small VPS with Docker Compose remains a hosting candidate, not a final decision. ChatGPT iPhone feasibility remains a Milestone 4 gate, not a Milestone 3 completion requirement. Full design: `docs/decisions/0003-m3-auth-security-design.md`.

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
| 7 | `.env.example` previously omitted runtime vars | **Resolved for M3.2/3.3:** documents `API_INTERNAL_URL`, `TEST_DATABASE_URL`, service credential, and Auth.js/Google vars. Unused `API_CORS_ORIGINS` / `NEXT_PUBLIC_API_BASE_URL` remain commented. |
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
- ~~Which authentication approach fits a single-user deployment, and how will the Next.js server authenticate to FastAPI?~~ **Answered in ADR 0003 and implemented in M3.2/M3.3:** Google sign-in with a verified-email allowlist, Auth.js v5 database sessions in PostgreSQL, protection of pages and Server Actions, a server-side service credential for Next.js→FastAPI. Scoped/revocable personal API tokens remain future Milestone 3 work.
- ~~How should backend CI obtain a Postgres `pcc_test` database?~~ **Answered:** a GitHub Actions Postgres service container.
- ~~Auth.js table migration ownership?~~ **Answered in M3.3:** Alembic revision `0003_authjs_tables` in the shared PCC database.
- What is the intended lifecycle of capture status values (`processing`, `processed`, `failed`), and which component owns the transitions?
- Should `projects` and `tasks` be kept, reshaped, or removed given that nothing uses them yet?
- Does the backend need a CORS policy, or should `API_CORS_ORIGINS` / `NEXT_PUBLIC_API_BASE_URL` be removed from `.env.example`?
- Is the known `.pth` "hidden flag" import issue (see `HANDOFF.md`) still occurring? Its root cause is unestablished and not investigated here. `pyproject.toml` includes `pythonpath = ["src"]` for pytest.

## C4. Maintenance

Update this document whenever the implemented architecture changes. Move an item from Part B to Part A only after the code exists and has been verified. Do not describe planned integrations, ingestion, or agents as implemented.
