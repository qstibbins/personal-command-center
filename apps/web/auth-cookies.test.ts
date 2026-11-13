import { describe, expect, it } from "vitest";

import {
  assertProductionAuthUrlConfigured,
  shouldUseSecureAuthCookies,
} from "./auth-cookies";

describe("shouldUseSecureAuthCookies", () => {
  it("is true when AUTH_URL is https", () => {
    expect(
      shouldUseSecureAuthCookies({ AUTH_URL: "https://pcc.example.com" }),
    ).toBe(true);
  });

  it("is false when AUTH_URL is http", () => {
    expect(
      shouldUseSecureAuthCookies({ AUTH_URL: "http://localhost:3000" }),
    ).toBe(false);
  });

  it("defaults to secure in production when AUTH_URL is unset", () => {
    expect(shouldUseSecureAuthCookies({ NODE_ENV: "production" })).toBe(true);
  });

  it("defaults to insecure in development when AUTH_URL is unset", () => {
    expect(shouldUseSecureAuthCookies({ NODE_ENV: "development" })).toBe(false);
  });
});

describe("assertProductionAuthUrlConfigured", () => {
  it("no-ops outside production", () => {
    expect(() =>
      assertProductionAuthUrlConfigured({ NODE_ENV: "development" }),
    ).not.toThrow();
  });

  it("skips during next production build", () => {
    expect(() =>
      assertProductionAuthUrlConfigured({
        NODE_ENV: "production",
        NEXT_PHASE: "phase-production-build",
      }),
    ).not.toThrow();
  });

  it("requires https AUTH_URL in production", () => {
    expect(() =>
      assertProductionAuthUrlConfigured({ NODE_ENV: "production" }),
    ).toThrow(/AUTH_URL must be set/);
    expect(() =>
      assertProductionAuthUrlConfigured({
        NODE_ENV: "production",
        AUTH_URL: "http://insecure.example",
      }),
    ).toThrow(/https/);
  });

  it("fails closed under PCC_ENV=production even if NODE_ENV differs", () => {
    // Container smoke sets PCC_ENV=production; Auth.js factory must still throw.
    expect(() =>
      assertProductionAuthUrlConfigured({
        NODE_ENV: "development",
        PCC_ENV: "production",
      }),
    ).toThrow(/AUTH_URL must be set/);
  });

  it("accepts https AUTH_URL in production", () => {
    expect(() =>
      assertProductionAuthUrlConfigured({
        NODE_ENV: "production",
        AUTH_URL: "https://pcc.example.com",
      }),
    ).not.toThrow();
  });
});
