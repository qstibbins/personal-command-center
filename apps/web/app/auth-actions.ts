"use server";

import { signOut } from "../auth";

/**
 * Sign out and revoke the Auth.js database session.
 * Auth.js deletes the sessions row for the opaque session token, so the
 * previous cookie cannot authorize protected pages or Server Actions.
 */
export async function signOutAction(): Promise<void> {
  await signOut({ redirectTo: "/signin" });
}
