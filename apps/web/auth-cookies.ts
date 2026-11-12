/**
 * Production cookie / host helpers for Auth.js (ADR 0003 / 0004).
 * Kept pure for unit tests — no Auth.js imports.
 */

export function shouldUseSecureAuthCookies(
  env: Record<string, string | undefined> = process.env,
): boolean {
  const authUrl = env.AUTH_URL?.trim();
  if (authUrl) {
    return authUrl.startsWith("https://");
  }
  // Fail closed toward Secure when NODE_ENV is production and AUTH_URL is unset.
  return env.NODE_ENV === "production";
}

/**
 * Prefer an explicit AUTH_URL in production so Auth.js does not rely solely on
 * Host-header inference behind Render's proxy (trustHost remains enabled).
 *
 * Skips during `next build` — Auth.js config is evaluated at build time with
 * placeholder env, before the real Render `AUTH_URL` exists.
 */
export function assertProductionAuthUrlConfigured(
  env: Record<string, string | undefined> = process.env,
): void {
  if (env.NEXT_PHASE === "phase-production-build") {
    return;
  }
  if (env.NODE_ENV !== "production" && env.PCC_ENV !== "production") {
    return;
  }
  const authUrl = env.AUTH_URL?.trim();
  if (!authUrl) {
    throw new Error(
      "AUTH_URL must be set to the canonical https:// origin in production (e.g. https://pcc.example.com).",
    );
  }
  if (!authUrl.startsWith("https://")) {
    throw new Error("AUTH_URL must use https:// in production.");
  }
}
