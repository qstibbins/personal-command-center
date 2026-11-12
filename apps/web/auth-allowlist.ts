/**
 * Server-only Google account allowlist helpers (ADR 0003).
 * Fail closed when the allowlist env var is missing or empty.
 */

/** Parse PCC_ALLOWED_GOOGLE_EMAILS (comma-separated). null = misconfigured. */
export function parseAllowedGoogleEmails(
  raw: string | undefined,
): string[] | null {
  if (raw === undefined || raw.trim() === "") {
    return null;
  }
  const emails = raw
    .split(",")
    .map((value) => value.trim().toLowerCase())
    .filter((value) => value.length > 0);
  return emails.length > 0 ? emails : null;
}

export function getAllowedGoogleEmails(): string[] | null {
  return parseAllowedGoogleEmails(process.env.PCC_ALLOWED_GOOGLE_EMAILS);
}

/** Case-insensitive exact match against the configured allowlist. */
export function isGoogleEmailAllowlisted(email: string | null | undefined): boolean {
  const allowed = getAllowedGoogleEmails();
  if (!allowed) {
    return false;
  }
  if (!email || typeof email !== "string") {
    return false;
  }
  return allowed.includes(email.trim().toLowerCase());
}

/**
 * Decide whether a Google OAuth profile may receive a PCC session.
 * Requires Google's verified email claim and an allowlist hit.
 */
export function evaluateGoogleSignInAccess(input: {
  email?: string | null;
  emailVerified?: boolean | null;
}): { allowed: true } | { allowed: false; reason: string } {
  const allowlist = getAllowedGoogleEmails();
  if (!allowlist) {
    return { allowed: false, reason: "allowlist_missing" };
  }
  if (input.emailVerified !== true) {
    return { allowed: false, reason: "email_unverified" };
  }
  const email = input.email?.trim().toLowerCase();
  if (!email) {
    return { allowed: false, reason: "email_missing" };
  }
  if (!allowlist.includes(email)) {
    return { allowed: false, reason: "email_not_allowlisted" };
  }
  return { allowed: true };
}
