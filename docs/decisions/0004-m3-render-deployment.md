# ADR 0004 — Milestone 3.5a Render deployment architecture

**Status:** Accepted. Milestone 3.5b implements repo prep (Dockerfiles, `render.yaml`, hardening, runbooks). No Render resources are provisioned by the ADR or by M3.5b alone.  
**Date:** 2026-11-12  
**Supersedes open hosting item in:** ADR 0003 § “Unresolved dependencies” item 1 (private ingress model)

## Context

Milestone 3 requires a secure private v0.1 deployment: HTTPS, protected UI/API, persistent PostgreSQL, backups, migrations, and health checks. Auth (ADR 0003) is implemented through Milestone 3.4 in code. Hosting remained open: ADR 0003 listed VPN-only vs public HTTPS + strict auth; `docs/ROADMAP.md` listed a small VPS + Docker Compose as a candidate only.

A planning assessment recommended managed hosting over a DIY VPS for current single-user scale, with Redis/RQ deferred because capture does not use them. The owner selected **Render** as the hosting provider for PCC v0.1.

This ADR records the deployment topology, trust boundaries, production configuration, operations ownership, and the follow-on M3.5b repo implementation plan. It does **not** create Render resources, purchase services, configure real OAuth credentials, or add deployment config files.

## Verified Render capabilities (re-check before purchase)

Evidence class **Verified** = confirmed against Render public docs on 2026-11-12. **Assumption** = pricing/ops detail that may change.

| Capability | Status | Evidence |
|---|---|---|
| Public HTTPS **web service** with TLS and custom domains | **Verified** | Render web services; Hobby includes custom domains |
| **Private service** (`pserv`): no public URL; reachable only on Render private network | **Verified** | [Private Services](https://render.com/docs/private-services), [Private Network](https://render.com/docs/private-network) |
| Same-region private networking between web, private service, and Postgres | **Verified** | Same docs; services must share account/workspace **and region** |
| Managed **Render Postgres** with **internal** connection URL for in-network services | **Verified** | [Create and Connect to Render Postgres](https://render.com/docs/postgresql-creating-connecting) |
| Restrict Postgres to private network only (`ipAllowList: []`) | **Verified** | Blueprint / Postgres networking docs |
| Blueprint wiring: `fromService` (private host/port) + `fromDatabase` (`connectionString`) | **Verified** | [Blueprint YAML Reference](https://render.com/docs/blueprint-spec) |
| Web-service HTTP **healthCheckPath**; failed new deploys keep prior instances | **Verified** | [Health Checks](https://render.com/docs/health-checks), [Deploys](https://render.com/docs/deploys) |
| Paid services: **preDeployCommand** (suitable for migrations) | **Verified** | Deploy docs (paid web/private/worker) |
| Manual **rollback** to a recent successful build artifact | **Verified** | [Rollbacks](https://render.com/docs/rollbacks) |
| Paid Postgres **PITR** (Hobby workspace: **3-day** window; Pro+: 7 days) + on-demand logical exports | **Verified** | [Postgres Recovery and Backups](https://render.com/docs/postgresql-backups) |
| Free Postgres expires (~30 days) / free web can sleep | **Verified** (unsuitable for PCC system-of-record) | Render pricing / Postgres docs |
| Private services have **no free compute tier** (paid starter required) | **Verified** | Render pricing / compute plans |

**Assumptions / re-verify before buy:**

- Illustrative Hobby compute floor: web **~$7**/mo + private service **~$7**/mo + Postgres basic **~$6**/mo ≈ **~$20**/mo before storage ($0.30/GB) and bandwidth over Hobby’s included allotment. Exact SKUs and names change; re-open [render.com/pricing](https://render.com/pricing).
- Postgres major version available on Render may differ from local Compose `postgres:17`; confirm supported major and set `postgresMajorVersion` deliberately.
- Private-service default listen port is commonly `10000` via `PORT`; apps must bind `0.0.0.0`, not `127.0.0.1`.
- HTTP health checks apply to **web** services; private services primarily get TCP/process checks unless product behavior changes — design API readiness for both deploy probes and app-level monitoring.

## Decision

### 1) Hosting provider

Use **Render** for PCC v0.1 production hosting on a **Hobby** workspace with **paid** compute for web, private API, and Postgres. Do **not** use Free Postgres or sleeping free web for personal capture data.

### 2) Service topology

```
Internet (HTTPS)
        │
        ▼
┌───────────────────────────┐
│ Render Web Service        │  Next.js (apps/web)
│ Public: PCC UI + Auth.js  │  Google OAuth callback
│ /api/auth/*, Server Actions│
└─────────────┬─────────────┘
              │ private network
              │ API_INTERNAL_URL → http://<pserv-host>:<port>
              │ Authorization: Bearer PCC_SERVICE_CREDENTIAL
              ▼
┌───────────────────────────┐
│ Render Private Service    │  FastAPI (apps/api)
│ No public URL             │  captures + api-tokens + health
└─────────────┬─────────────┘
              │ internal DATABASE_URL
              ▼
┌───────────────────────────┐
│ Render Postgres (managed) │  captures, Auth.js tables, api_tokens
│ Prefer private-only ACL   │
└───────────────────────────┘

Deferred for v0.1: Redis / Key Value, RQ worker, background workers.
```

| Component | Render type | Public? | Role |
|---|---|---|---|
| Next.js | Web service | Yes (HTTPS) | Only public ingress; Auth.js; Server Actions; Inbox UI |
| FastAPI | Private service | **No** | Capture + token management API; never exposed on the public internet for v0.1 |
| PostgreSQL | Managed Postgres | External URL exist but **restrict ACL** to private network for production | Shared app + Auth.js + `api_tokens` schema |
| Redis / worker | — | — | **Deferred** until Milestone 7 (or earlier if a real job appears) |

### 3) Network exposure model

**Public HTTPS + strict application auth** (not VPN-only).

- “Private” for v0.1 means private **data** and gated **access** (Google allowlist, service credential, hashed API tokens), not network obscurity of the website.
- FastAPI remains **network-private**; browsers never call it (existing architecture).
- Google OAuth requires a stable HTTPS origin on the web service.

### 4) Trust boundaries

1. **Public internet → Next.js only.** TLS terminated by Render. Browser holds only the Auth.js opaque session cookie.
2. **Next.js → FastAPI** over Render private network with `PCC_SERVICE_CREDENTIAL` (server-only). No `NEXT_PUBLIC_` secrets.
3. **FastAPI → Postgres** via **internal** connection string (same region). Prefer empty/public-deny IP allowlist so the DB is not broadly internet-reachable.
4. **Auth.js sessions** in Postgres remain authoritative for browser revocation (ADR 0003).
5. **Owner API tokens** authenticate to FastAPI; while FastAPI is private, those tokens are usable from the private network (and from Next.js management path). They are **not** a ChatGPT integration by themselves.
6. **Render platform** patches hosts; owner owns app auth, secrets, OAuth console, allowlist, `/docs` exposure policy, migration correctness, and backup drills.

### 5) Auth and secrets (production)

Carry forward ADR 0003. Production-specific requirements:

| Variable | Where set | Notes |
|---|---|---|
| `AUTH_SECRET` | Web (and only where Auth.js runs) | Strong random; never commit |
| `AUTH_GOOGLE_ID` / `AUTH_GOOGLE_SECRET` | Web | Google OAuth **Web** client |
| `AUTH_URL` | Web | Canonical public origin, e.g. `https://<custom-or-onrender-host>` |
| `PCC_ALLOWED_GOOGLE_EMAILS` | Web | Fail closed if empty |
| `PCC_SERVICE_CREDENTIAL` | Web **and** API (same value) | Rotate with optional `PCC_SERVICE_CREDENTIAL_PREVIOUS` on API |
| `API_INTERNAL_URL` | Web | Private-service base URL (`http://host:port`, no public hostname) |
| `DATABASE_URL` | API (+ Auth.js path on web) | Prefer Render **internal** URL; Auth.js may use `AUTH_DATABASE_URL` or rewrite of `DATABASE_URL` |
| `AUTH_DATABASE_URL` | Web (optional) | `postgresql://…` if driver rewrite of SQLAlchemy-style URL is undesirable |

Google Cloud Console (owner action, not agent):

- Authorized JavaScript origin: `https://<production-host>`
- Authorized redirect URI: `https://<production-host>/api/auth/callback/google`

Cookie / host security expectations:

- HTTPS at public ingress → Auth.js session cookie `Secure` in production.
- `SameSite=Lax` (ADR 0003) unless a verified cross-site need appears.
- Keep `trustHost` behavior consistent with documenting `AUTH_URL` explicitly in production so host inference is not ambiguous behind Render’s proxy.

### 6) Database migrations, backups, health, rollback

**Migration ownership**

- Alembic in `apps/api` remains the single schema owner (captures, Auth.js tables, `api_tokens`).
- Run `alembic upgrade head` as the API service **pre-deploy** command (paid private service), or an equivalent gated one-off job documented in M3.5b — never “migrate from laptop against prod by habit.”
- Migrations must be forward-compatible with zero-downtime web deploys where possible; destructive migrations need an explicit dual-write/expand-contract plan.

**Backup / restore expectations**

- Primary: Render paid Postgres **PITR** (Hobby: verify **3-day** window still current).
- Secondary: periodic **logical export** downloaded off-platform for longer retention (Render retains dashboard exports ~7 days — verify).
- At least one **restore drill** after first real deploy: PITR or logical restore into a scratch instance; confirm captures + sessions tables; document timestamp in handoff.
- Free Postgres is out of scope (no PITR / expiry).

**Health checks**

- Web: Render `healthCheckPath` on a lightweight Next.js route (or authenticated-safe public probe) that proves the process is up; prefer not to require Google session for the platform probe.
- API: keep `GET /api/v1/health` for liveness; M3.5b should add a **readiness** check that verifies Postgres connectivity (deep health). Do not require Redis while Redis is deferred.
- Production should disable or protect FastAPI `/docs` and `/openapi.json` (currently open).

**Deployment rollback**

- Prefer Render **Rollback** to a prior successful web/API deploy artifact for bad application releases.
- Rollback does **not** undo irreversible DB migrations; pair schema changes with expand/contract or restore-from-backup procedures.
- Failed health checks on a new deploy should leave the previous instance serving (platform behavior — Verified for web services).

### 7) Cost posture (illustrative; Assumption)

| Line item | Rough monthly | Notes |
|---|---|---|
| Web service (paid starter class) | ~$7 | Always-on; avoid free sleep |
| Private FastAPI | ~$7 | No free private-service tier |
| Postgres (paid basic class) | ~$6 + storage | Avoid free/expiring DB |
| Redis / worker | $0 for v0.1 | Deferred |
| Domain | ~$1 amortized | Optional custom domain |
| **Floor** | **~$20** | Plus bandwidth/storage; re-verify pricing |

Uncertainties: region, instance size if Node build/runtime needs more RAM, egress, logical-backup storage habits, and future Key Value when Milestone 7 lands (~+$10 class historically — Assumption).

### 8) Future ChatGPT / remote integration (explicitly unverified)

- Milestone 4 feasibility (mechanism, iPhone support, auth, reachability) remains **open**.
- v0.1’s **public Next.js + private FastAPI** does **not** by itself prove ChatGPT can call PCC.
- If Milestone 4 requires a tool host to reach PCC over the public internet, a later decision must add a **controlled public authenticated surface** (for example a minimal public FastAPI ingress, or a Next.js/BFF adapter) without abandoning allowlists/tokens. Do **not** expose FastAPI publicly in M3.5b “just in case.”
- Existing scoped API tokens remain the credential model candidate for non-browser clients once a reachable endpoint exists.

## Rejected alternatives

1. **Small VPS + Docker Compose + Caddy as v0.1 default** — Viable learning path, but higher OS/TLS/backup DIY burden for current scale. Remains a fallback if Render constraints appear.
2. **Railway (or other PaaS) instead of Render** — Acceptable managed alternative in the assessment; **rejected for v0.1** because the owner selected Render. Revisit only if Render blocks the topology.
3. **VPN-only / private website ingress** — Rejected: fights Google OAuth ergonomics and likely future remote/ChatGPT reachability.
4. **Public FastAPI in v0.1** — Rejected: unnecessary attack surface while the browser never calls the API; contradicts “do not expose FastAPI publicly.”
5. **Deploy Redis/RQ in v0.1** — Rejected: no product dependency yet; adds cost and failure modes.
6. **Free-tier sleeping web or expiring Postgres** — Rejected for a personal system of record.

## Milestone 3.5b — Repository implementation plan (docs → code later)

Documentation-only ADR acceptance does **not** implement these. Proposed sequence and acceptance criteria:

### M3.5b-1 — Containerize web and API

- Add production Dockerfiles (or Render-native build plans) for `apps/web` and `apps/api`.
- Next.js production build; uvicorn without `--reload`; bind `0.0.0.0`; no secrets in images.
- **Acceptance:** Local image builds succeed; API health responds in container; web build completes with placeholder Auth.js env (as CI already does).

### M3.5b-2 — Render Blueprint / service definitions (repo only)

- Add `render.yaml` (or equivalent documented dashboard steps) defining web + private API + Postgres; wire `API_INTERNAL_URL` via `fromService` and `DATABASE_URL` via `fromDatabase`; set Postgres `ipAllowList: []` for private-only intent.
- **Acceptance:** Blueprint validates against Render schema/docs; no real project created by agents unless owner requests provisioning.

### M3.5b-3 — Production hardening

- Deep readiness (Postgres); disable/protect `/docs` in production; document full prod env checklist including `AUTH_URL` and OAuth callback URLs.
- **Acceptance:** Readiness fails if DB is down; anonymous `/docs` not available in prod mode; env checklist merged.

### M3.5b-4 — Backup/restore + migrate runbook

- Document pre-deploy `alembic upgrade head`, PITR steps, logical export, and rollback caveats for migrations.
- **Acceptance:** Runbook in `docs/`; restore drill checkbox left for owner after real infra exists.

### M3.5b-5 — Owner provisioning gate (out of band)

- Create Render account/billing, domain, secrets, Google production OAuth URIs, allowlist; first deploy; auth + capture acceptance; backup drill.
- **Acceptance:** Milestone 3 exit criterion in `docs/ROADMAP.md`.

## Acceptance criteria for Milestone 3.5a (this ADR)

- [x] Render selected and topology documented (public Next.js, private FastAPI, managed Postgres).
- [x] Verified Render capabilities distinguished from assumptions/costs.
- [x] Trust boundaries and production env/OAuth callback expectations recorded.
- [x] Migration ownership, backup/restore, health, and rollback expectations recorded.
- [x] Redis/worker deferred; ChatGPT integration marked unverified with explicit future-surface note.
- [x] M3.5b implementation sequence with acceptance criteria defined.
- [ ] Owner has not yet provisioned Render (expected; not a blocker for ADR acceptance).

## Consequences

- Roadmap hosting choice is no longer “VPS candidate”; implementation work targets Render.
- M3.5b may add Dockerfiles and `render.yaml` without creating paid resources until the owner acts.
- Architecture diagrams and handoff next-step language should point here instead of leaving ingress undecided.
- ADR 0003’s open “private vs public HTTPS” item is resolved in favor of public HTTPS website + private API.

## References

- ADR 0003 — Authentication and API security design
- `docs/ROADMAP.md` Milestone 3
- `docs/ARCHITECTURE.md`
- Render docs: private services, private network, Postgres connect/backups, health checks, rollbacks, Blueprint spec, pricing (retrieved 2026-11-12)
