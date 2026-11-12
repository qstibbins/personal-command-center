import { describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import { resolveAuthDatabaseUrl } from "./auth-db";

describe("resolveAuthDatabaseUrl", () => {
  it("prefers AUTH_DATABASE_URL and leaves a standard postgres URL unchanged", () => {
    expect(
      resolveAuthDatabaseUrl({
        AUTH_DATABASE_URL: "postgresql://pcc:secret@localhost:5432/pcc",
        DATABASE_URL: "postgresql+psycopg://ignored",
      }),
    ).toBe("postgresql://pcc:secret@localhost:5432/pcc");
  });

  it("converts SQLAlchemy postgresql+psycopg URLs for the pg driver", () => {
    expect(
      resolveAuthDatabaseUrl({
        DATABASE_URL:
          "postgresql+psycopg://pcc:local_dev_only_change_me@localhost:5432/pcc",
      }),
    ).toBe("postgresql://pcc:local_dev_only_change_me@localhost:5432/pcc");
  });

  it("fails closed when no database URL is configured", () => {
    expect(() => resolveAuthDatabaseUrl({})).toThrow(
      /AUTH_DATABASE_URL or DATABASE_URL/,
    );
  });
});
