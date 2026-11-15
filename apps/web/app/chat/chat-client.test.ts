import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ChatApiError,
  cancelRun,
  createConversation,
  listConversations,
  listMessages,
  mergeMessagesById,
  sendMessageStream,
  sortConversations,
} from "./chat-client";
import type { ChatMessage, Conversation } from "./chat-types";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("chat client BFF helpers", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    fetchMock.mockReset();
  });

  it("lists conversations via same-origin BFF without owner_email", async () => {
    fetchMock.mockResolvedValue(jsonResponse([]));
    await listConversations({ limit: 10 });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/chat/conversations?limit=10");
    expect(init.credentials).toBe("same-origin");
    expect(JSON.stringify(init)).not.toContain("owner_email");
  });

  it("creates a mock conversation through the BFF", async () => {
    const conversation = {
      id: "c1",
      title: null,
      default_provider: "mock",
      default_model: "mock-echo-v1",
    };
    fetchMock.mockResolvedValue(jsonResponse(conversation, 201));
    const created = await createConversation();
    expect(created.id).toBe("c1");
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(String(init.body)) as Record<string, unknown>;
    expect(body.default_provider).toBe("mock");
    expect(body).not.toHaveProperty("owner_email");
  });

  it("loads messages for a conversation", async () => {
    fetchMock.mockResolvedValue(jsonResponse([]));
    await listMessages("conv-1");
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      "/api/chat/conversations/conv-1/messages",
    );
  });

  it("cancels a run through the BFF", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: "run-1", status: "cancelled" }));
    await cancelRun("run-1");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/chat/runs/run-1/cancel");
    expect(init.method).toBe("POST");
    const body = JSON.parse(String(init.body)) as Record<string, unknown>;
    expect(body).not.toHaveProperty("owner_email");
  });

  it("maps 409 run_in_progress on send", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          detail: {
            code: "run_in_progress",
            message: "Reply already in progress",
          },
        },
        409,
      ),
    );
    const result = await sendMessageStream({
      conversationId: "conv-1",
      content: "Hi",
      signal: new AbortController().signal,
      onEvent: () => undefined,
    });
    expect(result.ok).toBe(false);
    if (result.ok) throw new Error("expected failure");
    expect(result.error).toBeInstanceOf(ChatApiError);
    expect(result.error.status).toBe(409);
    expect(result.error.code).toBe("run_in_progress");
  });

  it("streams SSE content updates from the BFF body", async () => {
    const sse =
      'event: message_start\ndata: {"run_id":"r1","message_id":"m1"}\n\n' +
      'event: content_delta\ndata: {"message_id":"m1","delta":"Hi"}\n\n' +
      'event: message_end\ndata: {"message_id":"m1","status":"complete"}\n\n';
    fetchMock.mockResolvedValue(
      new Response(sse, {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      }),
    );
    const events: string[] = [];
    const result = await sendMessageStream({
      conversationId: "conv-1",
      content: "Hello",
      signal: new AbortController().signal,
      onEvent: (event) => events.push(event.event),
    });
    expect(result).toEqual({ ok: true, outcome: "completed" });
    expect(events).toEqual(["message_start", "content_delta", "message_end"]);
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(String(init.body)) as Record<string, unknown>;
    expect(body).toEqual({ content: "Hello" });
  });

  it("reports network failures without exposing credentials", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    const result = await sendMessageStream({
      conversationId: "conv-1",
      content: "Hello",
      signal: new AbortController().signal,
      onEvent: () => undefined,
    });
    expect(result.ok).toBe(false);
    if (result.ok) throw new Error("expected failure");
    expect(result.error.code).toBe("network_error");
    expect(result.error.message.toLowerCase()).not.toContain("bearer");
  });
});

describe("mergeMessagesById / sortConversations", () => {
  it("dedupes by id and sorts by sequence", () => {
    const a: ChatMessage = {
      id: "1",
      conversation_id: "c",
      owner_email: "o",
      role: "user",
      status: "complete",
      content_text: "A",
      provider: null,
      model: null,
      sequence: 2,
      error_code: null,
      error_message: null,
      created_at: "2026-01-01T00:00:00.000Z",
      updated_at: "2026-01-01T00:00:00.000Z",
      completed_at: null,
    };
    const b = { ...a, id: "2", sequence: 1, content_text: "B" };
    const merged = mergeMessagesById([a], [b, { ...a, content_text: "A2" }]);
    expect(merged.map((m) => m.id)).toEqual(["2", "1"]);
  });

  it("sorts conversations newest first", () => {
    const conversations = [
      { id: "old", updated_at: "2026-01-01T00:00:00.000Z" },
      { id: "new", updated_at: "2026-02-01T00:00:00.000Z" },
    ] as Conversation[];
    expect(sortConversations(conversations).map((c) => c.id)).toEqual([
      "new",
      "old",
    ]);
  });
});
