import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import { apiAuthHeaders, getApiBaseUrl } from "./api";

describe("getApiBaseUrl", () => {
  it("defaults to localhost when unset", () => {
    expect(getApiBaseUrl({})).toBe("http://localhost:8000");
  });

  it("prefers API_INTERNAL_URL", () => {
    expect(
      getApiBaseUrl({
        API_INTERNAL_URL: "http://pcc-api:10000/",
        API_INTERNAL_HOSTPORT: "ignored:9",
      }),
    ).toBe("http://pcc-api:10000");
  });

  it("builds http URL from Render hostport", () => {
    expect(
      getApiBaseUrl({ API_INTERNAL_HOSTPORT: "pcc-api-xxxx:10000" }),
    ).toBe("http://pcc-api-xxxx:10000");
  });

  it("accepts hostport that already includes a scheme", () => {
    expect(
      getApiBaseUrl({ API_INTERNAL_HOSTPORT: "http://pcc-api:10000/" }),
    ).toBe("http://pcc-api:10000");
  });
});

describe("apiAuthHeaders", () => {
  const original = process.env.PCC_SERVICE_CREDENTIAL;

  afterEach(() => {
    if (original === undefined) {
      delete process.env.PCC_SERVICE_CREDENTIAL;
    } else {
      process.env.PCC_SERVICE_CREDENTIAL = original;
    }
  });

  it("fails closed when the service credential is missing", () => {
    delete process.env.PCC_SERVICE_CREDENTIAL;
    expect(() => apiAuthHeaders()).toThrow(/PCC_SERVICE_CREDENTIAL is not set/);
  });

  it("returns Authorization bearer when configured", () => {
    process.env.PCC_SERVICE_CREDENTIAL = "unit-test-service-credential";
    expect(apiAuthHeaders({ Accept: "application/json" })).toEqual({
      Accept: "application/json",
      Authorization: "Bearer unit-test-service-credential",
    });
  });
});
