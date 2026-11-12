import NextAuth from "next-auth";
import Google from "next-auth/providers/google";
import PostgresAdapter from "@auth/pg-adapter";

import { evaluateGoogleSignInAccess, isGoogleEmailAllowlisted } from "./auth-allowlist";
import {
  assertProductionAuthUrlConfigured,
  shouldUseSecureAuthCookies,
} from "./auth-cookies";
import { getAuthPool } from "./auth-db";

/**
 * Auth.js v5 (next-auth@5 beta) with Google + PostgreSQL database sessions.
 * Config is a factory so the Postgres pool is created on first use (not at
 * module import), which keeps `next build` and unit tests workable without a
 * live database when auth paths are mocked or unused.
 *
 * Session strategy is explicitly "database" (ADR 0003) — never JWT.
 */
export const { handlers, auth, signIn, signOut } = NextAuth(() => {
  assertProductionAuthUrlConfigured();

  return {
    adapter: PostgresAdapter(getAuthPool()),
    providers: [
      Google({
        clientId: process.env.AUTH_GOOGLE_ID,
        clientSecret: process.env.AUTH_GOOGLE_SECRET,
      }),
    ],
    session: {
      strategy: "database",
      maxAge: 14 * 24 * 60 * 60,
    },
    pages: {
      signIn: "/signin",
      error: "/signin",
    },
    trustHost: true,
    useSecureCookies: shouldUseSecureAuthCookies(),
    callbacks: {
      async signIn({ account, profile }) {
        if (account?.provider !== "google") {
          return false;
        }
        const googleProfile = profile as
          | { email?: string | null; email_verified?: boolean | null }
          | undefined;
        const decision = evaluateGoogleSignInAccess({
          email: googleProfile?.email,
          emailVerified: googleProfile?.email_verified,
        });
        return decision.allowed;
      },
      async session({ session }) {
        const email = session.user?.email;
        if (!email || !isGoogleEmailAllowlisted(email)) {
          return { ...session, user: { ...session.user, email: undefined } };
        }
        return session;
      },
    },
  };
});
