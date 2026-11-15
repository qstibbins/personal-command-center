import { describe, expect, it } from "vitest";

import { mergeMessagesById } from "./chat-client";
import {
  bannerForHttpError,
  canSend,
  chatReducer,
  createInitialChatState,
  isActiveStream,
  makeTempIds,
} from "./chat-state";
import type { ChatMessage, Conversation } from "./chat-types";

const CONV_A: Conversation = {
  id: "conv-a",
  owner_email: "owner@example.com",
  title: "Alpha",
  status: "active",
  default_provider: "mock",
  default_model: "mock-echo-v1",
  system_prompt: null,
  next_sequence: 1,
  source: "pcc",
  created_at: "2026-01-01T00:00:00.000Z",
  updated_at: "2026-01-02T00:00:00.000Z",
  deleted_at: null,
};

const CONV_B: Conversation = {
  ...CONV_A,
  id: "conv-b",
  title: "Beta",
  updated_at: "2026-01-03T00:00:00.000Z",
};

function msg(
  partial: Partial<ChatMessage> & Pick<ChatMessage, "id" | "role" | "sequence">,
): ChatMessage {
  return {
    conversation_id: "conv-a",
    owner_email: "owner@example.com",
    status: "complete",
    content_text: "",
    provider: null,
    model: null,
    error_code: null,
    error_message: null,
    created_at: "2026-01-01T00:00:00.000Z",
    updated_at: "2026-01-01T00:00:00.000Z",
    completed_at: "2026-01-01T00:00:00.000Z",
    ...partial,
  };
}

describe("conversation selection and creation", () => {
  it("loads and sorts conversations by updated_at desc", () => {
    let state = createInitialChatState();
    state = chatReducer(state, { type: "conversations/loading" });
    expect(state.conversationsStatus).toBe("loading");

    state = chatReducer(state, {
      type: "conversations/loaded",
      conversations: [CONV_A, CONV_B],
    });
    expect(state.conversationsStatus).toBe("ready");
    expect(state.conversations.map((c) => c.id)).toEqual(["conv-b", "conv-a"]);
  });

  it("selects a conversation and clears prior messages", () => {
    let state = createInitialChatState({
      conversations: [CONV_A],
      conversationsStatus: "ready",
      activeConversationId: "conv-a",
      messages: [msg({ id: "m1", role: "user", sequence: 1, content_text: "hi" })],
      messagesStatus: "ready",
    });
    state = chatReducer(state, {
      type: "conversation/select",
      conversationId: "conv-b",
    });
    expect(state.activeConversationId).toBe("conv-b");
    expect(state.messages).toEqual([]);
    expect(state.messagesStatus).toBe("loading");
  });

  it("creates a conversation and makes it active with empty history", () => {
    let state = createInitialChatState({
      conversations: [CONV_A],
      conversationsStatus: "ready",
    });
    state = chatReducer(state, {
      type: "conversation/created",
      conversation: CONV_B,
    });
    expect(state.activeConversationId).toBe("conv-b");
    expect(state.messages).toEqual([]);
    expect(state.messagesStatus).toBe("ready");
    expect(state.conversations[0]?.id).toBe("conv-b");
  });

  it("surfaces conversation list errors", () => {
    let state = createInitialChatState();
    state = chatReducer(state, {
      type: "conversations/error",
      message: "Unable to load conversations.",
    });
    expect(state.conversationsStatus).toBe("error");
    expect(state.conversationsError).toContain("Unable to load");
  });
});

describe("history rendering and ordering", () => {
  it("keeps messages ordered by sequence after load", () => {
    let state = createInitialChatState({
      activeConversationId: "conv-a",
      messagesStatus: "loading",
    });
    state = chatReducer(state, {
      type: "messages/loaded",
      conversationId: "conv-a",
      messages: [
        msg({ id: "m2", role: "assistant", sequence: 2, content_text: "B" }),
        msg({ id: "m1", role: "user", sequence: 1, content_text: "A" }),
      ],
    });
    expect(state.messages.map((m) => m.content_text)).toEqual(["A", "B"]);
  });

  it("merges refreshed history without duplicating ids", () => {
    const localStreaming = msg({
      id: "asst-1",
      role: "assistant",
      sequence: 2,
      status: "streaming",
      content_text: "Hel",
    });
    const persisted = [
      msg({ id: "user-1", role: "user", sequence: 1, content_text: "Hi" }),
      msg({
        id: "asst-1",
        role: "assistant",
        sequence: 2,
        status: "complete",
        content_text: "Hello",
      }),
    ];
    const merged = mergeMessagesById(persisted, [localStreaming]);
    expect(merged).toHaveLength(2);
    expect(merged[1]?.content_text).toBe("Hello");
    expect(merged[1]?.status).toBe("complete");
  });

  it("preserves streaming locals when history refresh arrives mid-stream", () => {
    let state = createInitialChatState({
      activeConversationId: "conv-a",
      streamPhase: "streaming",
      streamingMessageId: "local-assistant-1",
      messages: [
        msg({
          id: "local-user-1",
          role: "user",
          sequence: 1,
          content_text: "Hi",
        }),
        msg({
          id: "local-assistant-1",
          role: "assistant",
          sequence: 2,
          status: "streaming",
          content_text: "Hel",
        }),
      ],
      messagesStatus: "ready",
    });
    state = chatReducer(state, {
      type: "messages/loaded",
      conversationId: "conv-a",
      messages: [
        msg({ id: "user-real", role: "user", sequence: 1, content_text: "Hi" }),
      ],
    });
    expect(state.messages.some((m) => m.id === "local-assistant-1")).toBe(true);
    expect(state.messages.some((m) => m.content_text === "Hel")).toBe(true);
  });
});

describe("streaming content updates", () => {
  it("appends deltas to the streaming assistant bubble", () => {
    let state = createInitialChatState({
      activeConversationId: "conv-a",
      messagesStatus: "ready",
    });
    expect(canSend(state)).toBe(true);
    const ids = makeTempIds(state.localSeq);
    const streamId = "stream-1";
    state = chatReducer(state, {
      type: "send/begin",
      conversationId: "conv-a",
      streamId,
      content: "Hello",
      tempUserId: ids.tempUserId,
      tempAssistantId: ids.tempAssistantId,
    });
    expect(state.streamPhase).toBe("sending");
    expect(state.activeStreamId).toBe(streamId);
    expect(canSend(state)).toBe(false);

    state = chatReducer(state, {
      type: "send/stream-event",
      streamId,
      event: {
        event: "message_start",
        data: { run_id: "run-1", message_id: "asst-real", role: "assistant" },
      },
    });
    expect(state.activeRunId).toBe("run-1");
    expect(state.streamingMessageId).toBe("asst-real");

    state = chatReducer(state, {
      type: "send/stream-event",
      streamId,
      event: {
        event: "content_delta",
        data: { message_id: "asst-real", delta: "Hel" },
      },
    });
    state = chatReducer(state, {
      type: "send/stream-event",
      streamId,
      event: {
        event: "content_delta",
        data: { message_id: "asst-real", delta: "lo" },
      },
    });
    const assistant = state.messages.find((m) => m.id === "asst-real");
    expect(assistant?.content_text).toBe("Hello");
    expect(assistant?.status).toBe("streaming");

    state = chatReducer(state, {
      type: "send/stream-event",
      streamId,
      event: {
        event: "message_end",
        data: { message_id: "asst-real", status: "complete", finish_reason: "stop" },
      },
    });
    expect(state.streamPhase).toBe("idle");
    expect(state.activeStreamId).toBeNull();
    expect(state.messages.at(-1)?.status).toBe("complete");
  });
});

describe("stop generation", () => {
  it("marks stream as stopping then partial on abort finish", () => {
    let state = createInitialChatState({
      activeConversationId: "conv-a",
      messagesStatus: "ready",
      streamPhase: "streaming",
      activeRunId: "run-1",
      streamingMessageId: "asst-1",
      activeStreamId: "stream-stop",
      activeStreamConversationId: "conv-a",
      messages: [
        msg({ id: "u1", role: "user", sequence: 1, content_text: "Hi" }),
        msg({
          id: "asst-1",
          role: "assistant",
          sequence: 2,
          status: "streaming",
          content_text: "Hel",
        }),
      ],
    });
    state = chatReducer(state, {
      type: "send/stop-requested",
      streamId: "stream-stop",
    });
    expect(state.streamPhase).toBe("stopping");
    state = chatReducer(state, {
      type: "send/finished",
      streamId: "stream-stop",
      outcome: "aborted",
    });
    expect(state.streamPhase).toBe("idle");
    expect(state.messages.at(-1)?.status).toBe("partial");
    expect(state.messages.at(-1)?.content_text).toBe("Hel");
  });
});

describe("duplicate-send prevention", () => {
  it("ignores send/begin while a stream is already active", () => {
    let state = createInitialChatState({
      activeConversationId: "conv-a",
      messagesStatus: "ready",
      streamPhase: "streaming",
      streamingMessageId: "asst-1",
      activeStreamId: "stream-live",
      activeStreamConversationId: "conv-a",
      messages: [
        msg({
          id: "asst-1",
          role: "assistant",
          sequence: 1,
          status: "streaming",
          content_text: "x",
        }),
      ],
    });
    expect(canSend(state)).toBe(false);
    const before = state.messages.length;
    state = chatReducer(state, {
      type: "send/begin",
      conversationId: "conv-a",
      streamId: "stream-dup",
      content: "again",
      tempUserId: "local-user-99",
      tempAssistantId: "local-assistant-99",
    });
    expect(state.messages).toHaveLength(before);
    expect(state.activeStreamId).toBe("stream-live");
  });
});

describe("partial and failed messages", () => {
  it("marks assistant as failed on stream error without partial", () => {
    let state = createInitialChatState({
      activeConversationId: "conv-a",
      streamPhase: "streaming",
      streamingMessageId: "asst-1",
      activeStreamId: "stream-err",
      activeStreamConversationId: "conv-a",
      messages: [
        msg({
          id: "asst-1",
          role: "assistant",
          sequence: 1,
          status: "streaming",
          content_text: "",
        }),
      ],
      messagesStatus: "ready",
    });
    state = chatReducer(state, {
      type: "send/stream-event",
      streamId: "stream-err",
      event: {
        event: "error",
        data: {
          message_id: "asst-1",
          code: "provider_error",
          message: "Mock forced error",
          partial: false,
        },
      },
    });
    expect(state.messages[0]?.status).toBe("failed");
    expect(state.banner?.kind).toBe("error");
    expect(state.streamPhase).toBe("idle");
  });

  it("keeps partial text when stream error reports partial", () => {
    let state = createInitialChatState({
      activeConversationId: "conv-a",
      streamPhase: "streaming",
      streamingMessageId: "asst-1",
      activeStreamId: "stream-partial",
      activeStreamConversationId: "conv-a",
      messages: [
        msg({
          id: "asst-1",
          role: "assistant",
          sequence: 1,
          status: "streaming",
          content_text: "partial text",
        }),
      ],
      messagesStatus: "ready",
    });
    state = chatReducer(state, {
      type: "send/stream-event",
      streamId: "stream-partial",
      event: {
        event: "error",
        data: {
          message_id: "asst-1",
          code: "cancelled",
          message: "Stopped",
          partial: true,
        },
      },
    });
    expect(state.messages[0]?.status).toBe("partial");
    expect(state.messages[0]?.content_text).toBe("partial text");
  });
});

describe("409 conflict behavior", () => {
  it("surfaces run_in_progress as non-fatal info banner and drops optimistic pair", () => {
    let state = createInitialChatState({
      activeConversationId: "conv-a",
      messagesStatus: "ready",
    });
    const ids = makeTempIds(0);
    state = chatReducer(state, {
      type: "send/begin",
      conversationId: "conv-a",
      streamId: "stream-409",
      content: "Hello",
      tempUserId: ids.tempUserId,
      tempAssistantId: ids.tempAssistantId,
    });
    expect(state.messages).toHaveLength(2);

    state = chatReducer(state, {
      type: "send/http-error",
      streamId: "stream-409",
      status: 409,
      code: "run_in_progress",
      message: "Reply already in progress",
    });
    expect(state.messages).toHaveLength(0);
    expect(state.banner).toEqual({
      kind: "info",
      code: "run_in_progress",
      message: "Reply already in progress",
    });
    expect(bannerForHttpError(409, "run_in_progress", "Reply already in progress").kind).toBe(
      "info",
    );
  });
});

describe("empty / loading / error states", () => {
  it("tracks message loading and error states for the active conversation", () => {
    let state = createInitialChatState({ activeConversationId: "conv-a" });
    state = chatReducer(state, {
      type: "messages/loading",
      conversationId: "conv-a",
    });
    expect(state.messagesStatus).toBe("loading");

    state = chatReducer(state, {
      type: "messages/error",
      conversationId: "conv-a",
      message: "Unable to load messages.",
    });
    expect(state.messagesStatus).toBe("error");
    expect(state.messagesError).toBe("Unable to load messages.");
  });

  it("ignores stale message loads for a previous conversation", () => {
    let state = createInitialChatState({
      activeConversationId: "conv-b",
      messagesStatus: "loading",
    });
    state = chatReducer(state, {
      type: "messages/loaded",
      conversationId: "conv-a",
      messages: [msg({ id: "m1", role: "user", sequence: 1, content_text: "stale" })],
    });
    expect(state.messages).toEqual([]);
    expect(state.messagesStatus).toBe("loading");
  });

  it("supports empty ready transcript with no messages", () => {
    const state = createInitialChatState({
      activeConversationId: "conv-a",
      messagesStatus: "ready",
      messages: [],
    });
    expect(state.messages).toHaveLength(0);
    expect(canSend(state)).toBe(true);
  });
});

describe("stale stream isolation after conversation switch", () => {
  function beginStream(
    conversationId: string,
    streamId: string,
    content = "Hello",
  ) {
    let state = createInitialChatState({
      conversations: [CONV_A, CONV_B],
      conversationsStatus: "ready",
      activeConversationId: conversationId,
      messagesStatus: "ready",
    });
    const ids = makeTempIds(state.localSeq);
    state = chatReducer(state, {
      type: "send/begin",
      conversationId,
      streamId,
      content,
      tempUserId: ids.tempUserId,
      tempAssistantId: ids.tempAssistantId,
    });
    return { state, ids, streamId };
  }

  it("A: ignores old content_delta after switching conversations", () => {
    const started = beginStream("conv-a", "stream-old");
    let state = started.state;
    state = chatReducer(state, {
      type: "send/stream-event",
      streamId: started.streamId,
      event: {
        event: "message_start",
        data: { run_id: "run-old", message_id: "asst-old", role: "assistant" },
      },
    });
    state = chatReducer(state, {
      type: "conversation/select",
      conversationId: "conv-b",
    });
    expect(state.activeStreamId).toBeNull();
    expect(state.streamPhase).toBe("idle");
    expect(canSend({ ...state, messagesStatus: "ready" })).toBe(true);

    const before = state;
    state = chatReducer(state, {
      type: "send/stream-event",
      streamId: "stream-old",
      event: {
        event: "content_delta",
        data: { message_id: "asst-old", delta: "stale" },
      },
    });
    expect(state.streamPhase).toBe("idle");
    expect(state.activeStreamId).toBeNull();
    expect(state.messages).toEqual(before.messages);
    expect(isActiveStream(state, "stream-old")).toBe(false);
  });

  it("B: ignores old message_start / message_end after switching", () => {
    const started = beginStream("conv-a", "stream-old");
    let state = chatReducer(started.state, {
      type: "conversation/select",
      conversationId: "conv-b",
    });

    state = chatReducer(state, {
      type: "send/stream-event",
      streamId: "stream-old",
      event: {
        event: "message_start",
        data: { run_id: "run-old", message_id: "asst-old", role: "assistant" },
      },
    });
    expect(state.streamPhase).toBe("idle");
    expect(state.activeRunId).toBeNull();

    state = chatReducer(state, {
      type: "send/stream-event",
      streamId: "stream-old",
      event: {
        event: "message_end",
        data: { message_id: "asst-old", status: "complete" },
      },
    });
    expect(state.streamPhase).toBe("idle");
    expect(state.messages).toEqual([]);
  });

  it("C: ignores old send/finished after a new conversation is active", () => {
    const started = beginStream("conv-a", "stream-old");
    let state = chatReducer(started.state, {
      type: "conversation/select",
      conversationId: "conv-b",
    });
    state = chatReducer(state, {
      type: "messages/loaded",
      conversationId: "conv-b",
      messages: [
        msg({
          id: "b1",
          role: "user",
          sequence: 1,
          content_text: "prior",
          conversation_id: "conv-b",
        }),
      ],
    });
    expect(canSend(state)).toBe(true);

    state = chatReducer(state, {
      type: "send/finished",
      streamId: "stream-old",
      outcome: "aborted",
    });
    expect(state.streamPhase).toBe("idle");
    expect(state.messages.map((m) => m.id)).toEqual(["b1"]);
    expect(canSend(state)).toBe(true);
  });

  it("D: old abort/finished cannot clear a newer active send", () => {
    const first = beginStream("conv-a", "stream-1");
    let state = chatReducer(first.state, {
      type: "conversation/select",
      conversationId: "conv-b",
    });
    state = chatReducer(state, {
      type: "messages/loaded",
      conversationId: "conv-b",
      messages: [],
    });
    const secondIds = makeTempIds(state.localSeq);
    state = chatReducer(state, {
      type: "send/begin",
      conversationId: "conv-b",
      streamId: "stream-2",
      content: "new turn",
      tempUserId: secondIds.tempUserId,
      tempAssistantId: secondIds.tempAssistantId,
    });
    expect(state.activeStreamId).toBe("stream-2");
    expect(state.streamPhase).toBe("sending");

    state = chatReducer(state, {
      type: "send/finished",
      streamId: "stream-1",
      outcome: "aborted",
    });
    expect(state.activeStreamId).toBe("stream-2");
    expect(state.streamPhase).toBe("sending");
    expect(canSend(state)).toBe(false);

    state = chatReducer(state, {
      type: "send/http-error",
      streamId: "stream-1",
      status: 0,
      code: "network_error",
      message: "stale",
    });
    expect(state.activeStreamId).toBe("stream-2");
    expect(state.streamPhase).toBe("sending");
  });

  it("E: switch away and back keeps Send usable without duplicating history", () => {
    const started = beginStream("conv-a", "stream-old");
    let state = chatReducer(started.state, {
      type: "conversation/select",
      conversationId: "conv-b",
    });
    state = chatReducer(state, {
      type: "conversation/select",
      conversationId: "conv-a",
    });
    const history = [
      msg({ id: "u1", role: "user", sequence: 1, content_text: "Hello" }),
      msg({
        id: "a1",
        role: "assistant",
        sequence: 2,
        status: "partial",
        content_text: "Hel",
      }),
    ];
    state = chatReducer(state, {
      type: "messages/loaded",
      conversationId: "conv-a",
      messages: history,
    });
    expect(state.messages).toHaveLength(2);
    expect(state.streamPhase).toBe("idle");
    expect(canSend(state)).toBe(true);

    // Stale reconcile for another conversation must not clobber.
    state = chatReducer(state, {
      type: "history/reconcile",
      conversationId: "conv-b",
      messages: [
        msg({
          id: "other",
          role: "user",
          sequence: 1,
          content_text: "nope",
          conversation_id: "conv-b",
        }),
      ],
    });
    expect(state.messages.map((m) => m.id)).toEqual(["u1", "a1"]);
  });

  it("F: active stream still updates and duplicate sends stay blocked", () => {
    const started = beginStream("conv-a", "stream-live");
    let state = started.state;
    state = chatReducer(state, {
      type: "send/stream-event",
      streamId: "stream-live",
      event: {
        event: "message_start",
        data: { run_id: "run-live", message_id: "asst-live", role: "assistant" },
      },
    });
    state = chatReducer(state, {
      type: "send/stream-event",
      streamId: "stream-live",
      event: {
        event: "content_delta",
        data: { message_id: "asst-live", delta: "OK" },
      },
    });
    expect(state.messages.find((m) => m.id === "asst-live")?.content_text).toBe(
      "OK",
    );
    expect(canSend(state)).toBe(false);

    const beforeLen = state.messages.length;
    state = chatReducer(state, {
      type: "send/begin",
      conversationId: "conv-a",
      streamId: "stream-dup",
      content: "nope",
      tempUserId: "local-user-dup",
      tempAssistantId: "local-assistant-dup",
    });
    expect(state.messages).toHaveLength(beforeLen);
    expect(state.activeStreamId).toBe("stream-live");
  });
});
