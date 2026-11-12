import "server-only";

import type { Session } from "next-auth";

import { auth } from "./auth";
import { isGoogleEmailAllowlisted } from "./auth-allowlist";

/**
 * Return the current allowlisted Auth.js database session, or null.
 * Used by pages and Server Actions — do not rely on middleware alone.
 */
export async function getAllowlistedSession(): Promise<Session | null> {
  const session = await auth();
  const email = session?.user?.email;
  if (!email || !isGoogleEmailAllowlisted(email)) {
    return null;
  }
  return session;
}

export async function requireAllowlistedSession(): Promise<Session> {
  const session = await getAllowlistedSession();
  if (!session) {
    throw new AuthRequiredError();
  }
  return session;
}

export class AuthRequiredError extends Error {
  constructor(message = "Authentication required") {
    super(message);
    this.name = "AuthRequiredError";
  }
}
