# Production environment checklist (Render / Milestone 3.5b)

Use with ADR 0004 and `render.yaml`. Do **not** commit real secrets.

## Services

| Service | Render type | Public? |
|---|---|---|
| `pcc-web` | Web | Yes (HTTPS) |
| `pcc-api` | Private service | **No** |
| `pcc-db` | Managed Postgres | Private ACL (`ipAllowList: []`) |

Redis / RQ worker: **not deployed** for v0.1.

## Required variables

### `pcc-web` (Next.js)

| Variable | Source | Notes |
|---|---|---|
| `NODE_ENV` | Blueprint `production` | |
| `PCC_ENV` | Blueprint `production` | |
| `AUTH_SECRET` | `generateValue` | Auth.js signing secret |
| `AUTH_URL` | Owner (`sync: false`) | Canonical `https://<host>` (custom domain or onrender.com) |
| `AUTH_GOOGLE_ID` | Owner | Google OAuth Web client ID |
| `AUTH_GOOGLE_SECRET` | Owner | Google OAuth client secret |
| `PCC_ALLOWED_GOOGLE_EMAILS` | Owner | Fail closed if empty; verified-email allowlist |
| `PCC_SERVICE_CREDENTIAL` | From `pcc-api` | Same Bearer secret as FastAPI |
| `API_INTERNAL_HOSTPORT` | From `pcc-api` `hostport` | App builds `http://host:port` |
| `DATABASE_URL` | From `pcc-db` internal URL | Auth.js sessions (`pg`) |

Optional: `AUTH_DATABASE_URL` if you prefer a dedicated `postgresql://` URL for Auth.js instead of rewriting `DATABASE_URL`.

**Chat BFF (Phase 1A.2 PR4):** `/api/chat/*` reuses the same `PCC_SERVICE_CREDENTIAL` + `API_INTERNAL_HOSTPORT` / `API_INTERNAL_URL`. No additional web secrets. `owner_email` is derived from the allowlisted Auth.js session only. Keep **exactly one non-overlapping `pcc-api` process** (PR3 abort/recovery); do not scale the private API for chat.

### `pcc-api` (FastAPI)

| Variable | Source | Notes |
|---|---|---|
| `PCC_ENV` | Blueprint `production` | Disables `/docs`, `/redoc`, `/openapi.json` |
| `PCC_SERVICE_CREDENTIAL` | `generateValue` | Shared with web |
| `PCC_CHAT_ASSUME_SINGLE_WORKER` | Blueprint `true` | Recovery gate only — still require one non-overlapping API process |
| `DATABASE_URL` | From `pcc-db` internal URL | Normalized to `postgresql+psycopg://` in app |
| `PORT` | Render | Default private-service port (commonly `10000`) |

Optional: `PCC_SERVICE_CREDENTIAL_PREVIOUS` during credential rotation (set in Dashboard; not in Blueprint by default).

Optional validation-only: `PCC_MOCK_STREAM_TEST` (`true` / `false`, default unset/`false`). When `true`, mock replies use a fixed ~10s timed stream for iPhone Stop testing. Does **not** enable `MOCK:*` hooks. Leave disabled in steady-state; changing it requires an API redeploy (see `docs/deploy/render-runbook.md` §4a).

## Google OAuth Console (owner)

After the public hostname is known:

1. Authorized JavaScript origin: `https://<production-host>`
2. Authorized redirect URI: `https://<production-host>/api/auth/callback/google`

Local URIs stay for development; do not remove them until unused.

## Cookie / host security

- `AUTH_URL` must be `https://…` in production.
- Auth.js `trustHost: true` with explicit `AUTH_URL`.
- `useSecureCookies` is enabled when `AUTH_URL` is https (or `NODE_ENV=production` if unset).
- Session strategy remains **database** (ADR 0003); allowlist unchanged.

## Health endpoints

| Path | Service | Purpose |
|---|---|---|
| `GET /api/health` | Web | Render `healthCheckPath` (liveness) |
| `GET /api/v1/health` | API | Liveness (no DB) |
| `GET /api/v1/ready` | API | Readiness (Postgres `SELECT 1`) |

## Do not

- Prefix secrets with `NEXT_PUBLIC_`
- Expose FastAPI publicly
- Put Redis in the Blueprint for v0.1
- Hardcode credentials in `render.yaml` or Dockerfiles
- Run Alembic from the web service (API `preDeployCommand` owns migrations)
