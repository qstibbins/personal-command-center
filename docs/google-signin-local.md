# Google sign-in local setup (Milestone 3.3)

Server-only Auth.js v5 Google sign-in with PostgreSQL database sessions.
Do not put OAuth secrets, `AUTH_SECRET`, the service credential, or the allowlist
in any `NEXT_PUBLIC_*` variable.

## 1. Google Cloud OAuth client

1. Open [Google Cloud Console](https://console.cloud.google.com/) → APIs & Services → Credentials.
2. Create an **OAuth 2.0 Client ID** of type **Web application**.
3. Authorized JavaScript origins (local):
   - `http://localhost:3000`
4. Authorized redirect URIs (local):
   - `http://localhost:3000/api/auth/callback/google`
5. Copy the client ID and client secret into your environment as
   `AUTH_GOOGLE_ID` and `AUTH_GOOGLE_SECRET` (see `.env.example`).

For a non-local deployment later, add the production origin and
`https://<your-host>/api/auth/callback/google`. Do not commit real credentials.

## 2. Environment variables

Copy `.env.example` to `.env` (and export the same values for both the API and
Next.js processes). Required for Google sign-in:

| Variable | Purpose |
|---|---|
| `AUTH_SECRET` | Auth.js signing/encryption secret (`openssl rand -base64 32`) |
| `AUTH_GOOGLE_ID` | Google OAuth client ID |
| `AUTH_GOOGLE_SECRET` | Google OAuth client secret |
| `PCC_ALLOWED_GOOGLE_EMAILS` | Comma-separated allowlist (initially one email). **Missing/empty fails closed.** |
| `DATABASE_URL` or `AUTH_DATABASE_URL` | Postgres for Auth.js tables (`postgresql+psycopg://` is rewritten for `pg`) |
| `PCC_SERVICE_CREDENTIAL` | Existing M3.2 Next.js→FastAPI Bearer secret (unchanged) |
| `API_INTERNAL_URL` | FastAPI base URL (default `http://localhost:8000`) |

Optional: `AUTH_URL=http://localhost:3000` if Auth.js cannot infer the origin.

## 3. Database migration

Auth.js tables (`users`, `accounts`, `sessions`, `verification_token`) are owned
by Alembic revision `0003_authjs_tables` in the same PostgreSQL database as PCC:

```bash
cd apps/api
uv run alembic upgrade head
```

Sign-out deletes the matching `sessions` row; an old session cookie alone cannot
authorize protected pages or Server Actions.

## 4. Run locally

1. `docker compose up -d`
2. Configure `.env` as above (allowlist = your Google account email).
3. Migrate: `cd apps/api && uv sync --group dev && uv run alembic upgrade head`
4. API: `uv run uvicorn pcc.main:app --reload --host 127.0.0.1 --port 8000`
5. Web (repo root, with env loaded): `pnpm install && pnpm dev:web`
6. Open `http://localhost:3000` → redirect to `/signin` → Sign in with Google.

## 5. Manual verification (requires real Google OAuth)

Automated tests cover allowlist / verified-email / missing-allowlist logic and
Server Action session gates with mocks. Still verify in a browser with real Google:

- [ ] Allowlisted verified account can sign in and use Capture + Inbox.
- [ ] A different Google account is denied (`AccessDenied` on `/signin`).
- [ ] Sign out returns to `/signin`; revisiting `/` stays signed out.
- [ ] After sign-out, an old session cookie cannot load captures or create one.
- [ ] View source / Network: no `AUTH_*`, allowlist, or service credential in JS.

## 6. Compatibility notes

- Auth.js via `next-auth@5` beta line (`5.0.0-beta.x`) with `@auth/pg-adapter` and `pg`.
- Verified against Next.js 15 / React 19 in this repository’s web package.
- Session strategy is explicitly `database` (not JWT).
- No Edge middleware is used for authorization; pages and Server Actions check
  the allowlisted session on the Node server runtime.
