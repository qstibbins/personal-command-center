import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

const getAllowlistedSessionMock = vi.fn();
vi.mock("../../../auth-session", () => ({
  getAllowlistedSession: (...args: unknown[]) =>
    getAllowlistedSessionMock(...args),
}));

import {
  proxyChatJson,
  proxyChatSse,
  resolveChatOwner,
  responseMentionsServiceCredential,
  unauthorizedJson,
  withSessionOwner,
} from "./bff";

const TEST_CREDENTIAL = "test-chat-bff-service-credential-secret";
const OWNER_SESSION = {
  user: { email: "Owner@Example.com", name: "Owner" },
  expires: "2099-01-01T00:00:00.000Z",
};

describe("chat BFF helpers", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    process.env.PCC_SERVICE_CREDENTIAL = TEST_CREDENTIAL;
    process.env.API_INTERNAL_URL = "http://pcc-api-test:8000";
    getAllowlistedSessionMock.mockResolvedValue(OWNER_SESSION);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    fetchMock.mockReset();
    getAllowlistedSessionMock.mockReset();
    delete process.env.PCC_SERVICE_CREDENTIAL;
    delete process.env.API_INTERNAL_URL;
  });

  it("resolveChatOwner normalizes allowlisted session email", async () => {
    const owner = await resolveChatOwner();
    expect(owner).toEqual({ email: "owner@example.com" });
  });

  it("resolveChatOwner returns null when unauthenticated", async () => {
    getAllowlistedSessionMock.mockResolvedValue(null);
    expect(await resolveChatOwner()).toBeNull();
  });

  it("withSessionOwner drops forged owner_email", () => {
    expect(
      withSessionOwner(
        { content: "hi", owner_email: "attacker@evil.test" },
        "owner@example.com",
      ),
    ).toEqual({ content: "hi", owner_email: "owner@example.com" });
  });

  it("unauthorizedJson returns 401 structured detail", async () => {
    const response = unauthorizedJson();
    expect(response.status).toBe(401);
    const body = await response.json();
    expect(body.detail.code).toBe("unauthenticated");
  });

  it("proxyChatJson injects session owner and service Authorization", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify([{ id: "c1" }]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const response = await proxyChatJson({
      path: "/api/v1/chat/conversations",
      method: "GET",
      ownerEmail: "owner@example.com",
      query: { limit: "10", owner_email: "forged@evil.test" },
    });

    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(
      "http://pcc-api-test:8000/api/v1/chat/conversations?limit=10&owner_email=owner%40example.com",
    );
    const headers = init.headers as Record<string, string>;
    expect(headers.Authorization).toBe(`Bearer ${TEST_CREDENTIAL}`);
    // Client-facing response must not echo the credential.
    const text = await response.text();
    expect(responseMentionsServiceCredential(text, TEST_CREDENTIAL)).toBe(
      false,
    );
  });

  it("proxyChatJson overwrites forged owner in POST body", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ id: "c1" }), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await proxyChatJson({
      path: "/api/v1/chat/conversations",
      method: "POST",
      ownerEmail: "owner@example.com",
      body: {
        title: "Hello",
        owner_email: "forged@evil.test",
        default_provider: "mock",
      },
    });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({
      title: "Hello",
      default_provider: "mock",
      owner_email: "owner@example.com",
    });
  });

  it("proxyChatJson forwards 409 run_in_progress bodies", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: { code: "run_in_progress", message: "busy" },
        }),
        { status: 409, headers: { "Content-Type": "application/json" } },
      ),
    );

    const response = await proxyChatJson({
      path: "/api/v1/chat/conversations/abc/messages",
      method: "DELETE",
      ownerEmail: "owner@example.com",
      body: {},
    });
    expect(response.status).toBe(409);
    const body = await response.json();
    expect(body.detail.code).toBe("run_in_progress");
  });

  it("proxyChatSse pipes the first chunk before upstream finishes", async () => {
    const encoder = new TextEncoder();
    let releaseRest!: () => void;
    const restGate = new Promise<void>((resolve) => {
      releaseRest = resolve;
    });

    const upstreamBody = new ReadableStream<Uint8Array>({
      async start(controller) {
        controller.enqueue(
          encoder.encode(
            'event: message_start\ndata: {"run_id":"r1","message_id":"m1","role":"assistant"}\n\n',
          ),
        );
        await restGate;
        controller.enqueue(
          encoder.encode(
            'event: content_delta\ndata: {"message_id":"m1","delta":"Hi"}\n\n',
          ),
        );
        controller.enqueue(
          encoder.encode(
            'event: message_end\ndata: {"message_id":"m1","status":"complete","finish_reason":"stop"}\n\n',
          ),
        );
        controller.close();
      },
    });

    fetchMock.mockResolvedValue(
      new Response(upstreamBody, {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      }),
    );

    const abort = new AbortController();
    const response = await proxyChatSse({
      path: "/api/v1/chat/conversations/c1/messages",
      ownerEmail: "owner@example.com",
      body: { content: "MOCK:SLOW", owner_email: "forged@evil.test" },
      signal: abort.signal,
    });

    expect(response.status).toBe(200);
    expect(response.headers.get("Content-Type")).toMatch(/text\/event-stream/);
    expect(response.headers.get("Cache-Control")).toMatch(/no-store/);
    expect(response.headers.get("X-Accel-Buffering")).toBe("no");

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body)).owner_email).toBe("owner@example.com");
    expect((init.headers as Record<string, string>).Authorization).toBe(
      `Bearer ${TEST_CREDENTIAL}`,
    );
    expect(init.signal).toBe(abort.signal);

    const reader = response.body!.getReader();
    const first = await reader.read();
    expect(first.done).toBe(false);
    const firstText = new TextDecoder().decode(first.value);
    expect(firstText).toContain("event: message_start");
    expect(firstText).toContain('"run_id":"r1"');
    // Upstream has not finished — second chunk still gated.
    expect(firstText).not.toContain("message_end");

    releaseRest();
    const chunks: string[] = [firstText];
    for (;;) {
      const next = await reader.read();
      if (next.done) break;
      chunks.push(new TextDecoder().decode(next.value));
    }
    const joined = chunks.join("");
    expect(joined).toContain("event: content_delta");
    expect(joined).toContain("event: message_end");
    expect(joined.indexOf("message_start")).toBeLessThan(
      joined.indexOf("content_delta"),
    );
    expect(joined.indexOf("content_delta")).toBeLessThan(
      joined.indexOf("message_end"),
    );
  });

  it("proxyChatSse forwards pre-stream 409 without pretending success", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: { code: "run_in_progress", message: "busy" },
        }),
        { status: 409, headers: { "Content-Type": "application/json" } },
      ),
    );

    const response = await proxyChatSse({
      path: "/api/v1/chat/conversations/c1/messages",
      ownerEmail: "owner@example.com",
      body: { content: "hi" },
      signal: new AbortController().signal,
    });
    expect(response.status).toBe(409);
    expect(response.headers.get("Content-Type")).toMatch(/application\/json/);
    const body = await response.json();
    expect(body.detail.code).toBe("run_in_progress");
  });

  it("proxyChatSse cancels the upstream reader when the browser aborts", async () => {
    const encoder = new TextEncoder();
    let cancelled = false;
    const upstreamBody = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(
          encoder.encode(
            'event: message_start\ndata: {"run_id":"r1","message_id":"m1","role":"assistant"}\n\n',
          ),
        );
      },
      cancel() {
        cancelled = true;
      },
    });

    fetchMock.mockResolvedValue(
      new Response(upstreamBody, {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      }),
    );

    const abort = new AbortController();
    const response = await proxyChatSse({
      path: "/api/v1/chat/conversations/c1/messages",
      ownerEmail: "owner@example.com",
      body: { content: "hi" },
      signal: abort.signal,
    });

    const reader = response.body!.getReader();
    await reader.read();
    await reader.cancel("browser disconnect");
    expect(cancelled).toBe(true);
  });

  it("proxyChatSse propagates fetch abort when signal is already aborted", async () => {
    const abort = new AbortController();
    abort.abort();
    fetchMock.mockImplementation((_url: string, init?: RequestInit) => {
      const signal = init?.signal;
      return Promise.reject(
        Object.assign(new Error("aborted"), { name: "AbortError", signal }),
      );
    });

    const response = await proxyChatSse({
      path: "/api/v1/chat/conversations/c1/messages",
      ownerEmail: "owner@example.com",
      body: { content: "hi" },
      signal: abort.signal,
    });
    expect(response.status).toBe(499);
  });

  it("proxyChatJson returns 502 when upstream is unreachable", async () => {
    fetchMock.mockRejectedValue(new Error("ECONNREFUSED"));
    const response = await proxyChatJson({
      path: "/api/v1/chat/conversations",
      method: "GET",
      ownerEmail: "owner@example.com",
    });
    expect(response.status).toBe(502);
    const body = await response.json();
    expect(body.detail.code).toBe("upstream_unreachable");
  });
});
