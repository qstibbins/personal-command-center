import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

const getAllowlistedSessionMock = vi.fn();
vi.mock("../../../auth-session", () => ({
  getAllowlistedSession: (...args: unknown[]) =>
    getAllowlistedSessionMock(...args),
}));

import {
  DELETE as deleteConversation,
  GET as getConversation,
  PATCH as patchConversation,
} from "./conversations/[conversationId]/route";
import {
  GET as getMessages,
  POST as postMessage,
} from "./conversations/[conversationId]/messages/route";
import {
  GET as listConversations,
  POST as createConversation,
} from "./conversations/route";
import { POST as cancelRun } from "./runs/[runId]/cancel/route";

const TEST_CREDENTIAL = "test-chat-route-service-credential-secret";
const OWNER_SESSION = {
  user: { email: "owner@example.com", name: "Owner" },
  expires: "2099-01-01T00:00:00.000Z",
};

const CONV_ID = "11111111-1111-4111-8111-111111111111";
const RUN_ID = "22222222-2222-4222-8222-222222222222";

function jsonRequest(
  url: string,
  init: { method?: string; body?: unknown; signal?: AbortSignal } = {},
): Request {
  return new Request(url, {
    method: init.method ?? "GET",
    headers: { "Content-Type": "application/json" },
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
    signal: init.signal,
  });
}

describe("chat BFF routes", () => {
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

  it("rejects unauthenticated list without calling FastAPI", async () => {
    getAllowlistedSessionMock.mockResolvedValue(null);
    const response = await listConversations(
      jsonRequest("http://localhost/api/chat/conversations"),
    );
    expect(response.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("lists conversations with session owner query only", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const response = await listConversations(
      jsonRequest(
        "http://localhost/api/chat/conversations?owner_email=forged@evil.test&limit=5",
      ),
    );
    expect(response.status).toBe(200);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("owner_email=owner%40example.com");
    expect(url).not.toContain("forged");
    expect((init.headers as Record<string, string>).Authorization).toBe(
      `Bearer ${TEST_CREDENTIAL}`,
    );
    const body = await response.text();
    expect(body).not.toContain(TEST_CREDENTIAL);
  });

  it("creates a conversation and ignores forged owner_email", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          id: CONV_ID,
          owner_email: "owner@example.com",
          title: "T",
          status: "active",
        }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      ),
    );

    const response = await createConversation(
      jsonRequest("http://localhost/api/chat/conversations", {
        method: "POST",
        body: {
          title: "T",
          owner_email: "forged@evil.test",
          default_provider: "mock",
          default_model: "mock-echo-v1",
        },
      }),
    );
    expect(response.status).toBe(201);
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body)).owner_email).toBe("owner@example.com");
  });

  it("gets / patches / deletes a conversation", async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify({ id: CONV_ID, status: "active" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    const params = Promise.resolve({ conversationId: CONV_ID });

    const got = await getConversation(
      jsonRequest(
        `http://localhost/api/chat/conversations/${CONV_ID}?owner_email=forged@evil.test`,
      ),
      { params },
    );
    expect(got.status).toBe(200);

    const patched = await patchConversation(
      jsonRequest(`http://localhost/api/chat/conversations/${CONV_ID}`, {
        method: "PATCH",
        body: { title: "Renamed", owner_email: "forged@evil.test" },
      }),
      { params },
    );
    expect(patched.status).toBe(200);

    const deleted = await deleteConversation(
      jsonRequest(`http://localhost/api/chat/conversations/${CONV_ID}`, {
        method: "DELETE",
        body: { owner_email: "forged@evil.test" },
      }),
      { params },
    );
    expect(deleted.status).toBe(200);

    expect(fetchMock).toHaveBeenCalledTimes(3);
    for (const call of fetchMock.mock.calls) {
      const [url, init] = call as [string, RequestInit];
      expect(url).toContain(`/api/v1/chat/conversations/${CONV_ID}`);
      if (init.body) {
        expect(JSON.parse(String(init.body)).owner_email).toBe(
          "owner@example.com",
        );
      } else {
        expect(url).toContain("owner_email=owner%40example.com");
      }
    }
  });

  it("forwards 404 for missing conversation", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: { code: "not_found", message: "Conversation not found" },
        }),
        { status: 404, headers: { "Content-Type": "application/json" } },
      ),
    );
    const response = await getConversation(
      jsonRequest(`http://localhost/api/chat/conversations/${CONV_ID}`),
      { params: Promise.resolve({ conversationId: CONV_ID }) },
    );
    expect(response.status).toBe(404);
    expect((await response.json()).detail.code).toBe("not_found");
  });

  it("loads message history", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const response = await getMessages(
      jsonRequest(
        `http://localhost/api/chat/conversations/${CONV_ID}/messages?limit=20`,
      ),
      { params: Promise.resolve({ conversationId: CONV_ID }) },
    );
    expect(response.status).toBe(200);
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain(`/messages?limit=20&owner_email=owner%40example.com`);
  });

  it("streams messages and preserves SSE framing order", async () => {
    const encoder = new TextEncoder();
    const payload =
      'event: message_start\ndata: {"run_id":"r1","message_id":"m1","role":"assistant"}\n\n' +
      'event: content_delta\ndata: {"message_id":"m1","delta":"Echo"}\n\n' +
      'event: message_end\ndata: {"message_id":"m1","status":"complete","finish_reason":"stop"}\n\n';

    fetchMock.mockResolvedValue(
      new Response(encoder.encode(payload), {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      }),
    );

    const response = await postMessage(
      jsonRequest(`http://localhost/api/chat/conversations/${CONV_ID}/messages`, {
        method: "POST",
        body: { content: "hello", owner_email: "forged@evil.test" },
      }),
      { params: Promise.resolve({ conversationId: CONV_ID }) },
    );

    expect(response.status).toBe(200);
    expect(response.headers.get("Content-Type")).toMatch(/text\/event-stream/);
    const text = await response.text();
    expect(text).toBe(payload);
    expect(text.indexOf("message_start")).toBeLessThan(
      text.indexOf("content_delta"),
    );
    expect(text.indexOf("content_delta")).toBeLessThan(
      text.indexOf("message_end"),
    );

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({
      content: "hello",
      owner_email: "owner@example.com",
    });
    expect(text).not.toContain(TEST_CREDENTIAL);
  });

  it("returns 409 from message POST without SSE success framing", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: {
            code: "run_in_progress",
            message: "A reply is already in progress",
          },
        }),
        { status: 409, headers: { "Content-Type": "application/json" } },
      ),
    );

    const response = await postMessage(
      jsonRequest(`http://localhost/api/chat/conversations/${CONV_ID}/messages`, {
        method: "POST",
        body: { content: "second" },
      }),
      { params: Promise.resolve({ conversationId: CONV_ID }) },
    );
    expect(response.status).toBe(409);
    expect(response.headers.get("Content-Type")).toMatch(/application\/json/);
    expect((await response.json()).detail.code).toBe("run_in_progress");
  });

  it("cancels a run with session owner", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          id: RUN_ID,
          status: "cancelled",
          cancel_reason: "client_stop",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const response = await cancelRun(
      jsonRequest(`http://localhost/api/chat/runs/${RUN_ID}/cancel`, {
        method: "POST",
        body: { owner_email: "forged@evil.test" },
      }),
      { params: Promise.resolve({ runId: RUN_ID }) },
    );
    expect(response.status).toBe(200);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(
      `http://pcc-api-test:8000/api/v1/chat/runs/${RUN_ID}/cancel`,
    );
    expect(JSON.parse(String(init.body)).owner_email).toBe("owner@example.com");
  });

  it("propagates browser abort to the upstream fetch signal on stream POST", async () => {
    const abort = new AbortController();
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: { code: "run_in_progress", message: "busy" },
        }),
        { status: 409, headers: { "Content-Type": "application/json" } },
      ),
    );

    await postMessage(
      jsonRequest(`http://localhost/api/chat/conversations/${CONV_ID}/messages`, {
        method: "POST",
        body: { content: "hi" },
        signal: abort.signal,
      }),
      { params: Promise.resolve({ conversationId: CONV_ID }) },
    );

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.signal).toBeInstanceOf(AbortSignal);
    expect(init.signal?.aborted).toBe(false);
    abort.abort();
    // Request may wrap the signal; aborting the browser controller must
    // abort the signal passed to upstream fetch.
    expect(init.signal?.aborted).toBe(true);
  });
});

