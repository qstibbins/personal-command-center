/**
 * Server-only helpers for calling FastAPI.
 * The service credential must never be imported into client components
 * or prefixed with NEXT_PUBLIC_.
 */

import "server-only";

const API_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

export function getApiBaseUrl(): string {
  return API_URL;
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
