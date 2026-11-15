# Render deployment runbook (Milestone 3.5b)

Companion to ADR 0004. This runbook is preparation only until the owner provisions a Render workspace.

## 1. Migration ownership and sequencing

| Rule | Detail |
|---|---|
| **Owner** | Alembic in `apps/api` (revisions through `0005_chat_schema`, including Auth.js, `api_tokens`, and chat tables) |
| **When** | `pcc-api` `preDeployCommand`: `alembic upgrade head` |
| **Who must not migrate** | `pcc-web` — no migration command (avoids concurrent Alembic) |
| **Failure behavior** | If pre-deploy exits non-zero, Render **cancels** that API deploy; the previous healthy API instance keeps serving |
| **Web dependency** | Auth.js needs `users` / `sessions` / … tables. Prefer **API deploy (with migrate) before relying on a fresh web instance** on first cutover |
| **Auto-deploy race** | Same-commit auto-deploys of web + API can race. For first production cutover, deploy/sync API first and confirm `/api/v1/ready`, then ensure web is live. For later schema changes that Auth.js needs, ship expand-only migrations before web code that depends on them |

Destructive / expand-contract migrations need an explicit plan; rollbacks do **not** undo schema.

## 2. First-time owner cutover (high level)

1. Create Render Hobby workspace + payment method (paid compute; no Free Postgres).
2. Apply Blueprint from repo `render.yaml` (**creates billable resources**).
3. Fill Dashboard prompts: `AUTH_URL`, Google OAuth ID/secret, `PCC_ALLOWED_GOOGLE_EMAILS`.
4. Confirm `PCC_SERVICE_CREDENTIAL` is shared (Blueprint wires web ← api).
5. Confirm DB region matches services; ACL remains private-only.
6. Wait for `pcc-api` pre-deploy migrate + healthy start; probe readiness from web logs or a one-off private-network check.
7. Confirm `pcc-web` health path `/api/health` passes; open `https://<host>/signin`.
8. Add Google production redirect URI; run allowlisted sign-in + capture acceptance.
9. Perform a backup / restore drill (below).

Agents must not perform steps that purchase or configure live OAuth secrets unless the owner explicitly requests it.

## 3. Chat API worker topology (Phase 1A)

See also ADR 0005 (`docs/decisions/0005-provider-neutral-chat.md`) and `docs/chat-architecture.md`.

Chat cancel/abort uses an **in-process** registry. MVP requires **exactly one active `pcc-api` process**.

`PCC_CHAT_ASSUME_SINGLE_WORKER=true` (default; set in `render.yaml`) only **gates** abandoned-run recovery. It does **not** enforce single-process deployment or prevent a second worker from starting.

| Constraint | Detail |
|---|---|
| Exactly one process | Do not scale `pcc-api` horizontally. |
| No rolling overlap | Stop the old API process before the new one accepts traffic (or accept brief downtime). Default Render behavior that keeps the previous instance serving while the new deploy becomes healthy creates an **overlap window** where the new process can incorrectly finalize the old process’s live `running` rows. |
| Multi-worker cancel/recovery | **Unsupported.** Cancel on process B cannot signal process A’s generator; recovery treats peer live runs as abandoned. |
| Flag alone | Setting `PCC_CHAT_ASSUME_SINGLE_WORKER=false` disables recovery (stuck `running` / 409 risk) without enabling safe multi-worker cancel. |

| Event | Behavior |
|---|---|
| Process crash mid-stream | In-flight assistant buffer is lost (by design). On next API start / claim / delete / cancel, abandoned `chat_runs.status='running'` rows with **no** local abort handle are finalized (`cancelled` / `superseded` or `client_stop`) so the one-running unique index is released. |
| Soft-delete while streaming | **HTTP 409** `run_in_progress` while a live run is active. |
| Claim vs recovery | Abort handle is registered **before** the `running` row commits so same-process recovery cannot steal a newly claimed live run. |

Recovery never uses wall-clock timeouts to kill a slow but live stream; liveness is “local abort handle present.”

## 4. Routine deploy

1. Merge to the Blueprint-tracked branch.
2. Render builds Docker images for changed services.
3. `pcc-api`: build → **`alembic upgrade head`** → start → private network (**one instance** for chat).
4. `pcc-web`: build → health check `/api/health` → public traffic.
5. Smoke: sign-in, create capture, list Inbox, sign-out.

## 5. Application rollback

1. Render Dashboard → service → Deploys → **Rollback** to a prior successful deploy.
2. Rollback restores the prior **build artifact** / start config for that service; it does **not** reverse Alembic.
3. If a bad migration already applied, use expand-contract forward fix or **database** recovery (PITR / logical restore)—not app rollback alone.
4. After emergency rollback, disable auto-deploy until the fix is confirmed (Render rollback does not disable auto-deploy by itself).

## 6. Backup and restore

### Point-in-time recovery (PITR)

- **Availability:** paid Render Postgres only (not Free).
- **Window (verify before relying):** Hobby workspace **3 days**; Pro+ **7 days** (Render docs as of ADR 0004 date).
- **Behavior:** PITR creates a **new** database instance at the chosen timestamp (not in-place overwrite). You cannot restore to within ~10 minutes of “now.”
- **Billing:** the recovery instance is a **full billed Postgres instance** until you delete or suspend it. Plan cutover cost before drilling.
- **Cutover:** validate data → point `DATABASE_URL` / Blueprint `fromDatabase` at the recovery instance → delete/suspend the old primary when stable.

### Logical exports

- Trigger from the database Recovery page; download `.dir.tar.gz` for off-platform retention.
- Render retains dashboard exports ~**7 days** (verify); keep your own copies for longer.
- Prefer PITR for recent accidents; logical dumps for portable/offsite copies.

### Restore drill (acceptance)

After first real deploy, record in `docs/HANDOFF.md`:

- [ ] PITR or logical restore into a scratch instance
- [ ] Captures + Auth.js tables present
- [ ] Timestamp and operator notes

## 7. Cost notes (assumptions — re-check pricing)

| Item | Rough cost | Notes |
|---|---|---|
| Web `0.5c-512mb` | ~$7/mo | Always-on; Node `max-old-space-size=384` |
| Private API `0.5c-512mb` | ~$7/mo | No free private-service tier |
| Postgres `0.1c-256mb` | ~$6/mo + storage | Avoid Free (expiry / no PITR) |
| **Steady floor** | **~$20/mo** | Plus bandwidth over Hobby allotment |
| Docker **build** minutes | Platform build pipeline | Builds consume build time/resources separate from runtime; heavy Next.js builds may need retries or a larger runtime plan if the running service OOMs |
| **PITR recovery instance** | Same class as DB plan while alive | Delete after cutover or drill |
| Redis / worker | $0 in v0.1 | Deferred |

If `pcc-web` OOMs on 512MB RAM, upgrade web to `1c-2g` (~$25/mo class) rather than adding swap hacks.

## 8. Security checklist at deploy time

- [ ] FastAPI is **private** (`pserv`) — no public URL
- [ ] `/docs` / `/redoc` / `/openapi.json` return 404 with `PCC_ENV=production`
- [ ] No service credential or OAuth secrets in client bundles
- [ ] Google allowlist set; non-allowlisted accounts denied
- [ ] Postgres ACL private-only
- [ ] `AUTH_URL` https; Secure cookies in production

## 9. ChatGPT / Milestone 4

Do **not** expose FastAPI publicly for speculative ChatGPT access. Milestone 4 must verify client support first. A later controlled public authenticated surface may be required; scoped API tokens alone against a private service are not reachable from the internet.
