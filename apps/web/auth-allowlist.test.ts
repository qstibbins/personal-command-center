import { afterEach, describe, expect, it } from "vitest";

import {
  evaluateGoogleSignInAccess,
  isGoogleEmailAllowlisted,
  parseAllowedGoogleEmails,
} from "./auth-allowlist";

describe("parseAllowedGoogleEmails", () => {
  it("fails closed for undefined, empty, and whitespace-only values", () => {
    expect(parseAllowedGoogleEmails(undefined)).toBeNull();
    expect(parseAllowedGoogleEmails("")).toBeNull();
    expect(parseAllowedGoogleEmails("   ")).toBeNull();
    expect(parseAllowedGoogleEmails(", ,")).toBeNull();
  });

  it("parses a single email and normalizes case and whitespace", () => {
    expect(parseAllowedGoogleEmails("  Owner@Example.COM ")).toEqual([
      "owner@example.com",
    ]);
  });

  it("parses a comma-separated allowlist", () => {
    expect(
      parseAllowedGoogleEmails("a@example.com, B@Example.com ,c@example.com"),
    ).toEqual(["a@example.com", "b@example.com", "c@example.com"]);
  });
});

describe("evaluateGoogleSignInAccess", () => {
  const original = process.env.PCC_ALLOWED_GOOGLE_EMAILS;

  afterEach(() => {
    if (original === undefined) {
      delete process.env.PCC_ALLOWED_GOOGLE_EMAILS;
    } else {
      process.env.PCC_ALLOWED_GOOGLE_EMAILS = original;
    }
  });

  it("fails closed when the allowlist is missing", () => {
    delete process.env.PCC_ALLOWED_GOOGLE_EMAILS;
    expect(
      evaluateGoogleSignInAccess({
        email: "owner@example.com",
        emailVerified: true,
      }),
    ).toEqual({ allowed: false, reason: "allowlist_missing" });
  });

  it("denies unverified Google email even when allowlisted", () => {
    process.env.PCC_ALLOWED_GOOGLE_EMAILS = "owner@example.com";
    expect(
      evaluateGoogleSignInAccess({
        email: "owner@example.com",
        emailVerified: false,
      }),
    ).toEqual({ allowed: false, reason: "email_unverified" });
    expect(
      evaluateGoogleSignInAccess({
        email: "owner@example.com",
        emailVerified: null,
      }),
    ).toEqual({ allowed: false, reason: "email_unverified" });
  });

  it("denies allowlisted email when the verified claim is absent", () => {
    process.env.PCC_ALLOWED_GOOGLE_EMAILS = "owner@example.com";
    expect(
      evaluateGoogleSignInAccess({
        email: "owner@example.com",
      }),
    ).toEqual({ allowed: false, reason: "email_unverified" });
  });

  it("denies non-allowlisted verified Google accounts", () => {
    process.env.PCC_ALLOWED_GOOGLE_EMAILS = "owner@example.com";
    expect(
      evaluateGoogleSignInAccess({
        email: "other@example.com",
        emailVerified: true,
      }),
    ).toEqual({ allowed: false, reason: "email_not_allowlisted" });
  });

  it("allows the allowlisted verified Google account (case-insensitive)", () => {
    process.env.PCC_ALLOWED_GOOGLE_EMAILS = "owner@example.com";
    expect(
      evaluateGoogleSignInAccess({
        email: "Owner@Example.com",
        emailVerified: true,
      }),
    ).toEqual({ allowed: true });
  });

  it("denies missing email", () => {
    process.env.PCC_ALLOWED_GOOGLE_EMAILS = "owner@example.com";
    expect(
      evaluateGoogleSignInAccess({
        email: null,
        emailVerified: true,
      }),
    ).toEqual({ allowed: false, reason: "email_missing" });
  });
});

describe("isGoogleEmailAllowlisted", () => {
  const original = process.env.PCC_ALLOWED_GOOGLE_EMAILS;

  afterEach(() => {
    if (original === undefined) {
      delete process.env.PCC_ALLOWED_GOOGLE_EMAILS;
    } else {
      process.env.PCC_ALLOWED_GOOGLE_EMAILS = original;
    }
  });

  it("returns false when allowlist is missing", () => {
    delete process.env.PCC_ALLOWED_GOOGLE_EMAILS;
    expect(isGoogleEmailAllowlisted("owner@example.com")).toBe(false);
  });

  it("matches allowlisted emails case-insensitively", () => {
    process.env.PCC_ALLOWED_GOOGLE_EMAILS = "owner@example.com";
    expect(isGoogleEmailAllowlisted("Owner@Example.com")).toBe(true);
    expect(isGoogleEmailAllowlisted("other@example.com")).toBe(false);
    expect(isGoogleEmailAllowlisted(null)).toBe(false);
  });
});
