import { describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import { getApiBaseUrl } from "./api";

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
