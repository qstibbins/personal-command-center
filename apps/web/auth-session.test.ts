import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

const authMock = vi.fn();
vi.mock("./auth", () => ({
  auth: (...args: unknown[]) => authMock(...args),
}));

import { getAllowlistedSession } from "./auth-session";

describe("getAllowlistedSession", () => {
  const original = process.env.PCC_ALLOWED_GOOGLE_EMAILS;

  beforeEach(() => {
    process.env.PCC_ALLOWED_GOOGLE_EMAILS = "owner@example.com";
    authMock.mockReset();
  });

  afterEach(() => {
    if (original === undefined) {
      delete process.env.PCC_ALLOWED_GOOGLE_EMAILS;
    } else {
      process.env.PCC_ALLOWED_GOOGLE_EMAILS = original;
    }
  });

  it("returns null when Auth.js has no session (signed out / revoked cookie)", async () => {
    authMock.mockResolvedValue(null);
    expect(await getAllowlistedSession()).toBeNull();
  });

  it("returns null when the session email is not allowlisted", async () => {
    authMock.mockResolvedValue({
      user: { email: "intruder@example.com" },
      expires: "2099-01-01T00:00:00.000Z",
    });
    expect(await getAllowlistedSession()).toBeNull();
  });

  it("returns the session for the allowlisted account", async () => {
    const session = {
      user: { email: "owner@example.com", name: "Owner" },
      expires: "2099-01-01T00:00:00.000Z",
    };
    authMock.mockResolvedValue(session);
    expect(await getAllowlistedSession()).toEqual(session);
  });

  it("fails closed when the allowlist env var is missing", async () => {
    delete process.env.PCC_ALLOWED_GOOGLE_EMAILS;
    authMock.mockResolvedValue({
      user: { email: "owner@example.com" },
      expires: "2099-01-01T00:00:00.000Z",
    });
    expect(await getAllowlistedSession()).toBeNull();
  });
});
