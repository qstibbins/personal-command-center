import "server-only";

import { Pool } from "pg";

/**
 * Convert SQLAlchemy-style URLs (postgresql+psycopg://) to a libpq URL
 * that `pg` accepts. Prefer AUTH_DATABASE_URL when set.
 */
export function resolveAuthDatabaseUrl(
  env: Record<string, string | undefined> = process.env,
): string {
  const raw = env.AUTH_DATABASE_URL ?? env.DATABASE_URL;
  if (!raw || !raw.trim()) {
    throw new Error(
      "AUTH_DATABASE_URL or DATABASE_URL must be set for Auth.js database sessions.",
    );
  }
  return raw.trim().replace(/^postgresql\+psycopg:/i, "postgresql:");
}

const globalForAuth = globalThis as typeof globalThis & {
  __pccAuthPgPool?: Pool;
};

export function getAuthPool(): Pool {
  if (!globalForAuth.__pccAuthPgPool) {
    globalForAuth.__pccAuthPgPool = new Pool({
      connectionString: resolveAuthDatabaseUrl(),
      max: 10,
      idleTimeoutMillis: 30_000,
      connectionTimeoutMillis: 5_000,
    });
  }
  return globalForAuth.__pccAuthPgPool;
}
