/**
 * Milestone 3.5b.2 — exercise the real Next.js API client helpers in-container.
 *
 * Loads apps/web/app/api.ts (getApiBaseUrl + apiAuthHeaders) and uses those
 * helpers for the same FastAPI calls page.tsx (Inbox) and createCapture use
 * after Auth.js allows the request.
 *
 * Limitation: invoking the fully authenticated createCapture Server Action
 * requires a real Google OAuth / Auth.js database session. This script does
 * NOT bypass Auth.js, mint production-only test sessions, or weaken allowlist
 * checks. It verifies the deepest feasible application path: the shared
 * server-only API client over the private web→API network.
 *
 * Env:
 *   PCC_API_CLIENT_MODULE — absolute path to apps/web/app/api.ts
 *   PCC_SERVICE_CREDENTIAL / API_INTERNAL_URL / API_INTERNAL_HOSTPORT — as in web
 */
import { pathToFileURL } from "node:url";

const modulePath = process.env.PCC_API_CLIENT_MODULE?.trim();
if (!modulePath) {
  console.error(
    "PCC_API_CLIENT_MODULE must point at apps/web/app/api.ts (absolute path).",
  );
  process.exit(1);
}

const { getApiBaseUrl, apiAuthHeaders } = await import(
  pathToFileURL(modulePath).href
);

const base = getApiBaseUrl();
if (!base || base.includes("localhost")) {
  // In the disposable private network we expect Render-style hostport wiring.
  // Fail loudly if helpers fell back to the local-dev default.
  if (!process.env.API_INTERNAL_URL && !process.env.API_INTERNAL_HOSTPORT) {
    console.error(
      "getApiBaseUrl fell back without API_INTERNAL_URL/HOSTPORT; refusing.",
    );
    process.exit(1);
  }
}

console.log(`application-path api base: ${base}`);

const health = await fetch(`${base}/api/v1/health`, { cache: "no-store" });
if (!health.ok) {
  throw new Error(`health via getApiBaseUrl failed: ${health.status}`);
}

const ready = await fetch(`${base}/api/v1/ready`, { cache: "no-store" });
if (!ready.ok) {
  throw new Error(`ready via getApiBaseUrl failed: ${ready.status}`);
}

const denied = await fetch(`${base}/api/v1/captures`, { cache: "no-store" });
if (denied.status !== 401) {
  throw new Error(`expected unauthenticated captures 401, got ${denied.status}`);
}

// Mirrors apps/web/app/page.tsx getCaptures() — service credential via apiAuthHeaders.
const list = await fetch(`${base}/api/v1/captures`, {
  cache: "no-store",
  headers: apiAuthHeaders(),
});
if (!list.ok) {
  throw new Error(`captures list via apiAuthHeaders failed: ${list.status}`);
}

// Mirrors the FastAPI fetch inside createCapture after session gate succeeds.
const create = await fetch(`${base}/api/v1/captures`, {
  method: "POST",
  headers: apiAuthHeaders({ "Content-Type": "application/json" }),
  body: JSON.stringify({
    source_type: "text",
    title: "verify-app-path",
    content: "m3.5b.2 application-path verification via api.ts helpers",
  }),
});
if (create.status !== 201 && create.status !== 200) {
  throw new Error(`captures create via apiAuthHeaders failed: ${create.status}`);
}

const created = await create.json();
if (!created?.id || created.title !== "verify-app-path") {
  throw new Error("captures create returned unexpected body");
}

console.log("application-path web API client checks ok");
