/**
 * Server-only helpers for calling FastAPI.
 * The service credential must never be imported into client components
 * or prefixed with NEXT_PUBLIC_.
 */

import "server-only";

/**
 * Resolve the FastAPI base URL for server-side fetches.
 *
 * Prefer `API_INTERNAL_URL` (full URL). On Render, Blueprints can inject
 * `API_INTERNAL_HOSTPORT` (`host:port` from a private service); we prefix
 * `http://` because private-network traffic is plain HTTP.
 */
export function getApiBaseUrl(
  env: Record<string, string | undefined> = process.env,
): string {
  const explicit = env.API_INTERNAL_URL?.trim();
  if (explicit) {
    return explicit.replace(/\/$/, "");
  }
  const hostPort = env.API_INTERNAL_HOSTPORT?.trim();
  if (hostPort) {
    if (hostPort.startsWith("http://") || hostPort.startsWith("https://")) {
      return hostPort.replace(/\/$/, "");
    }
    return `http://${hostPort}`;
  }
  return "http://localhost:8000";
}

/** Authorization headers for privileged FastAPI calls (captures). */
export function apiAuthHeaders(
  extra: Record<string, string> = {},
): Record<string, string> {
  const credential = process.env.PCC_SERVICE_CREDENTIAL;
  if (!credential) {
    throw new Error(
      "PCC_SERVICE_CREDENTIAL is not set. Configure the server-only service credential.",
    );
  }
  return {
    ...extra,
    Authorization: `Bearer ${credential}`,
  };
}
