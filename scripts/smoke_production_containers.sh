#!/usr/bin/env bash
# Milestone 3.5b.1 / 3.5b.2 — disposable production container smoke tests.
# Builds are expected to be loaded as pcc-api:verify and pcc-web:verify.
# Does not push images, provision Render, or use live secrets.
# M3.5b.2 exercises apps/web/app/api.ts helpers (not raw Node fetch) and
# tightens the AUTH_URL fail-closed assertion to an expected 5xx mode.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

API_IMAGE="${API_IMAGE:-pcc-api:verify}"
WEB_IMAGE="${WEB_IMAGE:-pcc-web:verify}"
NETWORK="${NETWORK:-pcc-verify}"
DB_NAME="${DB_NAME:-pcc-db}"
API_NAME="${API_NAME:-pcc-api}"
WEB_NAME="${WEB_NAME:-pcc-web}"
API_BAD_DB_NAME="${API_BAD_DB_NAME:-pcc-api-bad-db}"
API_NO_CRED_NAME="${API_NO_CRED_NAME:-pcc-api-no-cred}"
WEB_NO_AUTH_URL_NAME="${WEB_NO_AUTH_URL_NAME:-pcc-web-no-auth-url}"

# Disposable CI-only values — never real production secrets.
DB_USER=pcc
DB_PASSWORD=pcc_verify_ci_only
DB_DB=pcc
SERVICE_CREDENTIAL=ci-only-disposable-service-credential-not-for-prod
AUTH_SECRET=ci-only-not-a-real-auth-secret
AUTH_URL=https://ci.example.invalid

DATABASE_URL_SQLALCHEMY="postgresql+psycopg://${DB_USER}:${DB_PASSWORD}@${DB_NAME}:5432/${DB_DB}"
DATABASE_URL_PG="postgresql://${DB_USER}:${DB_PASSWORD}@${DB_NAME}:5432/${DB_DB}"

log() { printf '==> %s\n' "$*"; }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

cleanup() {
  local ec=$?
  set +e
  docker rm -f \
    "$WEB_NAME" "$API_NAME" "$API_BAD_DB_NAME" "$API_NO_CRED_NAME" \
    "$WEB_NO_AUTH_URL_NAME" "$DB_NAME" >/dev/null 2>&1
  docker network rm "$NETWORK" >/dev/null 2>&1
  exit "$ec"
}
trap cleanup EXIT

require_image() {
  docker image inspect "$1" >/dev/null 2>&1 || fail "missing image $1 (build it first)"
}

wait_http() {
  local url="$1"
  local expect_code="${2:-200}"
  local attempts="${3:-40}"
  local i code
  for i in $(seq 1 "$attempts"); do
    code="$(
      docker run --rm --network "$NETWORK" curlimages/curl:8.12.1 \
        -s -o /dev/null -w '%{http_code}' --connect-timeout 2 --max-time 5 \
        "$url" || true
    )"
    if [[ "$code" == "$expect_code" ]]; then
      return 0
    fi
    sleep 2
  done
  fail "timed out waiting for HTTP $expect_code from $url (last=$code)"
}

http_code() {
  local url="$1"
  shift
  docker run --rm --network "$NETWORK" curlimages/curl:8.12.1 \
    -s -o /dev/null -w '%{http_code}' --connect-timeout 2 --max-time 10 \
    "$@" "$url"
}

http_body() {
  local url="$1"
  shift
  docker run --rm --network "$NETWORK" curlimages/curl:8.12.1 \
    -s --connect-timeout 2 --max-time 10 \
    "$@" "$url"
}

psql_q() {
  docker run --rm --network "$NETWORK" postgres:16-alpine \
    psql "$DATABASE_URL_PG" -v ON_ERROR_STOP=1 -Atc "$1"
}

require_image "$API_IMAGE"
require_image "$WEB_IMAGE"

log "Creating disposable Docker network"
docker network create "$NETWORK" >/dev/null

log "Starting fresh PostgreSQL 16 (matches Render Blueprint major)"
docker run -d \
  --name "$DB_NAME" \
  --network "$NETWORK" \
  --network-alias pcc-db \
  -e POSTGRES_USER="$DB_USER" \
  -e POSTGRES_PASSWORD="$DB_PASSWORD" \
  -e POSTGRES_DB="$DB_DB" \
  postgres:16-alpine >/dev/null

for i in $(seq 1 40); do
  if docker run --rm --network "$NETWORK" postgres:16-alpine \
    pg_isready -h "$DB_NAME" -U "$DB_USER" -d "$DB_DB" >/dev/null 2>&1; then
    break
  fi
  if [[ "$i" -eq 40 ]]; then
    fail "postgres did not become ready"
  fi
  sleep 1
done

log "Running Alembic migrations inside the API image (preDeploy analogue)"
docker run --rm --network "$NETWORK" \
  -e DATABASE_URL="$DATABASE_URL_SQLALCHEMY" \
  -e PCC_ENV=production \
  -e PCC_SERVICE_CREDENTIAL="$SERVICE_CREDENTIAL" \
  --entrypoint alembic \
  "$API_IMAGE" upgrade head

log "Verifying Auth.js + API-token + capture tables and migration head"
docker run --rm --network "$NETWORK" \
  -e DATABASE_URL="$DATABASE_URL_SQLALCHEMY" \
  -v "$ROOT/scripts/verify_production_schema.py:/tmp/verify_production_schema.py:ro" \
  --entrypoint python \
  "$API_IMAGE" /tmp/verify_production_schema.py

log "Starting API container on port 10000 (Render private-service default)"
docker run -d \
  --name "$API_NAME" \
  --network "$NETWORK" \
  --network-alias pcc-api \
  -e PCC_ENV=production \
  -e PCC_SERVICE_CREDENTIAL="$SERVICE_CREDENTIAL" \
  -e DATABASE_URL="$DATABASE_URL_SQLALCHEMY" \
  -e PORT=10000 \
  "$API_IMAGE" >/dev/null

wait_http "http://${API_NAME}:10000/api/v1/health" 200
health_body="$(http_body "http://${API_NAME}:10000/api/v1/health")"
[[ "$health_body" == *'"status":"ok"'* ]] || [[ "$health_body" == *'"status": "ok"'* ]] \
  || fail "unexpected health body: $health_body"

wait_http "http://${API_NAME}:10000/api/v1/ready" 200
ready_body="$(http_body "http://${API_NAME}:10000/api/v1/ready")"
[[ "$ready_body" == *'"database":"ok"'* ]] || [[ "$ready_body" == *'"database": "ok"'* ]] \
  || fail "unexpected ready body: $ready_body"

docs_code="$(http_code "http://${API_NAME}:10000/docs")"
[[ "$docs_code" == "404" ]] || fail "production /docs must be 404, got $docs_code"
openapi_code="$(http_code "http://${API_NAME}:10000/openapi.json")"
[[ "$openapi_code" == "404" ]] || fail "production /openapi.json must be 404, got $openapi_code"

unauth_code="$(http_code "http://${API_NAME}:10000/api/v1/captures")"
[[ "$unauth_code" == "401" ]] || fail "unauthenticated captures must be 401, got $unauth_code"

log "Starting web container on port 3000 with disposable Auth.js placeholders"
docker run -d \
  --name "$WEB_NAME" \
  --network "$NETWORK" \
  --network-alias pcc-web \
  -e NODE_ENV=production \
  -e PCC_ENV=production \
  -e AUTH_SECRET="$AUTH_SECRET" \
  -e AUTH_URL="$AUTH_URL" \
  -e AUTH_GOOGLE_ID=ci-placeholder-client-id \
  -e AUTH_GOOGLE_SECRET=ci-placeholder-client-secret \
  -e PCC_ALLOWED_GOOGLE_EMAILS=ci@example.com \
  -e PCC_SERVICE_CREDENTIAL="$SERVICE_CREDENTIAL" \
  -e API_INTERNAL_HOSTPORT="${API_NAME}:10000" \
  -e DATABASE_URL="$DATABASE_URL_PG" \
  -e PORT=3000 \
  -e HOSTNAME=0.0.0.0 \
  "$WEB_IMAGE" >/dev/null

wait_http "http://${WEB_NAME}:3000/api/health" 200
web_health="$(http_body "http://${WEB_NAME}:3000/api/health")"
[[ "$web_health" == *'"status":"ok"'* ]] || [[ "$web_health" == *'"status": "ok"'* ]] \
  || fail "unexpected web health body: $web_health"
[[ "$web_health" == *'pcc-web'* ]] || fail "web health missing service id: $web_health"

log "Application path: real apps/web/app/api.ts helpers → API (private network)"
# One-shot container from the production web image, same network/env wiring as
# the running web service. Loads getApiBaseUrl + apiAuthHeaders from source
# (server-only stubbed for Node). Does not bypass Auth.js or invent sessions.
docker run --rm --network "$NETWORK" \
  --user root \
  -e NODE_ENV=production \
  -e PCC_ENV=production \
  -e PCC_SERVICE_CREDENTIAL="$SERVICE_CREDENTIAL" \
  -e API_INTERNAL_HOSTPORT="${API_NAME}:10000" \
  -e PCC_API_CLIENT_MODULE=/verify/api.ts \
  -v "$ROOT/apps/web/app/api.ts:/verify/api.ts:ro" \
  -v "$ROOT/scripts/verify_web_api_client.mjs:/verify/verify_web_api_client.mjs:ro" \
  -v "$ROOT/scripts/hooks:/verify/hooks:ro" \
  --entrypoint node \
  "$WEB_IMAGE" \
  --experimental-strip-types \
  --import /verify/hooks/register-server-only.mjs \
  /verify/verify_web_api_client.mjs

capture_count="$(psql_q "SELECT count(*) FROM captures WHERE title = 'verify-app-path';")"
[[ "$capture_count" -ge 1 ]] || fail "capture from application-path API client was not persisted"

log "Negative: API readiness fails closed when database is unreachable"
docker run -d \
  --name "$API_BAD_DB_NAME" \
  --network "$NETWORK" \
  -e PCC_ENV=production \
  -e PCC_SERVICE_CREDENTIAL="$SERVICE_CREDENTIAL" \
  -e DATABASE_URL="postgresql+psycopg://pcc:bad@127.0.0.1:1/pcc" \
  -e PORT=10001 \
  "$API_IMAGE" >/dev/null
wait_http "http://${API_BAD_DB_NAME}:10001/api/v1/health" 200
wait_http "http://${API_BAD_DB_NAME}:10001/api/v1/ready" 503
bad_ready="$(http_body "http://${API_BAD_DB_NAME}:10001/api/v1/ready")"
[[ "$bad_ready" != *connection* ]] || fail "ready error leaked connection details"
[[ "$bad_ready" == *'"database":"error"'* ]] || [[ "$bad_ready" == *'"database": "error"'* ]] \
  || fail "unexpected bad-db ready body: $bad_ready"

log "Negative: empty PCC_SERVICE_CREDENTIAL rejects authenticated callers (fail closed)"
docker run -d \
  --name "$API_NO_CRED_NAME" \
  --network "$NETWORK" \
  -e PCC_ENV=production \
  -e PCC_SERVICE_CREDENTIAL= \
  -e DATABASE_URL="$DATABASE_URL_SQLALCHEMY" \
  -e PORT=10002 \
  "$API_IMAGE" >/dev/null
wait_http "http://${API_NO_CRED_NAME}:10002/api/v1/health" 200
no_cred_code="$(
  http_code "http://${API_NO_CRED_NAME}:10002/api/v1/captures" \
    -H "Authorization: Bearer ${SERVICE_CREDENTIAL}"
)"
[[ "$no_cred_code" == "401" ]] || fail "empty service credential must 401, got $no_cred_code"

log "Negative: production web without AUTH_URL fails closed on Auth.js routes"
docker run -d \
  --name "$WEB_NO_AUTH_URL_NAME" \
  --network "$NETWORK" \
  -e NODE_ENV=production \
  -e PCC_ENV=production \
  -e AUTH_SECRET="$AUTH_SECRET" \
  -e AUTH_GOOGLE_ID=ci-placeholder-client-id \
  -e AUTH_GOOGLE_SECRET=ci-placeholder-client-secret \
  -e PCC_ALLOWED_GOOGLE_EMAILS=ci@example.com \
  -e PCC_SERVICE_CREDENTIAL="$SERVICE_CREDENTIAL" \
  -e API_INTERNAL_HOSTPORT="${API_NAME}:10000" \
  -e DATABASE_URL="$DATABASE_URL_PG" \
  -e PORT=3001 \
  -e HOSTNAME=0.0.0.0 \
  "$WEB_IMAGE" >/dev/null
wait_http "http://${WEB_NO_AUTH_URL_NAME}:3001/api/health" 200
# Liveness stays up; Auth.js config must fail closed when AUTH_URL is missing.
# Expected mode: assertProductionAuthUrlConfigured throws → route returns 5xx.
# Do not accept arbitrary 4xx; do not assert incidental Next.js HTML wording.
auth_code="$(http_code "http://${WEB_NO_AUTH_URL_NAME}:3001/api/auth/session")"
case "$auth_code" in
  500|502|503) ;;
  *)
    fail "expected Auth.js AUTH_URL fail-closed 5xx (500/502/503), got $auth_code"
    ;;
esac
auth_logs="$(docker logs "$WEB_NO_AUTH_URL_NAME" 2>&1 || true)"
[[ "$auth_logs" == *AUTH_URL* ]] \
  || fail "expected AUTH_URL configuration error in web container logs"

log "All production container verification checks passed"
echo "PASS: images build/load assumed; migrate; health/ready; app-path api client; negatives"
