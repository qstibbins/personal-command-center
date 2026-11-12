import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));
vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));

const getAllowlistedSessionMock = vi.fn();
vi.mock("../auth-session", () => ({
  getAllowlistedSession: (...args: unknown[]) =>
    getAllowlistedSessionMock(...args),
}));

import { revalidatePath } from "next/cache";

import {
  createApiTokenAction,
  listApiTokensAction,
  revokeApiTokenAction,
} from "./api-tokens-actions";
import { initialCreateApiTokenState } from "./api-tokens-state";

const TEST_SERVICE_CREDENTIAL = "test-web-service-credential-not-for-production";
const ALLOWLISTED_SESSION = {
  user: { email: "owner@example.com", name: "Owner" },
  expires: "2099-01-01T00:00:00.000Z",
};

const RAW_TOKEN = "pcc_at_test-raw-token-value-only-once";

function makeForm(fields: Record<string, string>) {
  const formData = new FormData();
  for (const [key, value] of Object.entries(fields)) formData.set(key, value);
  return formData;
}

describe("API token server actions", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    process.env.PCC_SERVICE_CREDENTIAL = TEST_SERVICE_CREDENTIAL;
    getAllowlistedSessionMock.mockResolvedValue(ALLOWLISTED_SESSION);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    fetchMock.mockReset();
    getAllowlistedSessionMock.mockReset();
    vi.mocked(revalidatePath).mockReset();
    delete process.env.PCC_SERVICE_CREDENTIAL;
  });

  it("refuses create without an allowlisted session and does not call FastAPI", async () => {
    getAllowlistedSessionMock.mockResolvedValue(null);
    const state = await createApiTokenAction(
      initialCreateApiTokenState,
      makeForm({ label: "T", scope_read: "on" }),
    );
    expect(state.status).toBe("error");
    expect(state.message).toMatch(/sign in/i);
    expect(state.revealedToken).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("creates a token, reveals it once, and never returns the service credential", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({
        id: "11111111-1111-4111-8111-111111111111",
        label: "Integration",
        token_prefix: "pcc_at_test",
        scopes: ["captures:write"],
        created_at: "2026-11-12T00:00:00Z",
        expires_at: null,
        revoked_at: null,
        created_by_email: "owner@example.com",
        token: RAW_TOKEN,
      }),
    });

    const state = await createApiTokenAction(
      initialCreateApiTokenState,
      makeForm({ label: " Integration ", scope_write: "on" }),
    );

    expect(state.status).toBe("success");
    expect(state.revealedToken).toBe(RAW_TOKEN);
    expect(revalidatePath).toHaveBeenCalledWith("/settings/api-tokens");

    const [, init] = fetchMock.mock.calls[0];
    const body = JSON.parse(init.body);
    expect(body).toEqual({
      label: "Integration",
      scopes: ["captures:write"],
      created_by_email: "owner@example.com",
    });
    expect(init.headers.Authorization).toBe(`Bearer ${TEST_SERVICE_CREDENTIAL}`);
    expect(JSON.stringify(state)).not.toContain(TEST_SERVICE_CREDENTIAL);
  });

  it("requires at least one scope", async () => {
    const state = await createApiTokenAction(
      initialCreateApiTokenState,
      makeForm({ label: "No scopes" }),
    );
    expect(state.status).toBe("error");
    expect(state.message).toMatch(/scope/i);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("lists tokens without exposing a raw token field from the action contract", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [
        {
          id: "11111111-1111-4111-8111-111111111111",
          label: "Integration",
          token_prefix: "pcc_at_test",
          scopes: ["captures:read"],
          created_at: "2026-11-12T00:00:00Z",
          expires_at: null,
          revoked_at: null,
          created_by_email: "owner@example.com",
        },
      ],
    });

    const result = await listApiTokensAction();
    expect(result.error).toBeNull();
    expect(result.tokens).toHaveLength(1);
    expect(result.tokens?.[0]).not.toHaveProperty("token");
    expect(JSON.stringify(result)).not.toContain(TEST_SERVICE_CREDENTIAL);
  });

  it("revokes a token after session check", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        id: "11111111-1111-4111-8111-111111111111",
        label: "Integration",
        token_prefix: "pcc_at_test",
        scopes: ["captures:read"],
        created_at: "2026-11-12T00:00:00Z",
        expires_at: null,
        revoked_at: "2026-11-12T01:00:00Z",
        created_by_email: "owner@example.com",
      }),
    });

    const result = await revokeApiTokenAction(
      "11111111-1111-4111-8111-111111111111",
    );
    expect(result.ok).toBe(true);
    expect(fetchMock.mock.calls[0][0]).toContain(
      "/api/v1/api-tokens/11111111-1111-4111-8111-111111111111/revoke",
    );
    expect(JSON.stringify(result)).not.toContain(TEST_SERVICE_CREDENTIAL);
  });

  it("fails closed for list and revoke without a session", async () => {
    getAllowlistedSessionMock.mockResolvedValue(null);
    expect(await listApiTokensAction()).toEqual({
      tokens: null,
      error: "You must sign in to manage API tokens.",
    });
    expect(await revokeApiTokenAction("x")).toEqual({
      ok: false,
      message: "You must sign in to revoke API tokens.",
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
