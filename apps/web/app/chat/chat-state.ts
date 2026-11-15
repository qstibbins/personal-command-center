/**
 * Pure chat UI state helpers / reducer for PR5.
 * Keeps stream, history merge, and send-guard logic testable without React.
 */

import { mergeMessagesById, sortConversations } from "./chat-client";
import type {
  ChatBanner,
  ChatMessage,
  ChatUiState,
  Conversation,
  ParsedSseEvent,
  StreamPhase,
} from "./chat-types";

export function createInitialChatState(
  partial?: Partial<ChatUiState>,
): ChatUiState {
  return {
    conversations: [],
    conversationsStatus: "idle",
    conversationsError: null,
    activeConversationId: null,
    messages: [],
    messagesStatus: "idle",
    messagesError: null,
    streamPhase: "idle",
    activeRunId: null,
    streamingMessageId: null,
    banner: null,
    localSeq: 0,
    ...partial,
  };
}

export type ChatAction =
  | { type: "conversations/loading" }
  | {
      type: "conversations/loaded";
      conversations: Conversation[];
    }
  | { type: "conversations/error"; message: string }
  | { type: "conversation/created"; conversation: Conversation }
  | { type: "conversation/upsert"; conversation: Conversation }
  | { type: "conversation/select"; conversationId: string | null }
  | { type: "messages/loading"; conversationId: string }
  | {
      type: "messages/loaded";
      conversationId: string;
      messages: ChatMessage[];
    }
  | { type: "messages/error"; conversationId: string; message: string }
  | { type: "banner/set"; banner: ChatBanner | null }
  | { type: "banner/clear" }
  | {
      type: "send/begin";
      conversationId: string;
      content: string;
      tempUserId: string;
      tempAssistantId: string;
    }
  | { type: "send/stream-event"; event: ParsedSseEvent }
  | {
      type: "send/http-error";
      status: number;
      code: string;
      message: string;
    }
  | { type: "send/stop-requested" }
  | {
      type: "send/finished";
      outcome: "completed" | "aborted" | "interrupted" | "failed";
    }
  | { type: "history/reconcile"; messages: ChatMessage[] };

export function canSend(state: ChatUiState): boolean {
  return (
    state.streamPhase === "idle" &&
    state.activeConversationId !== null &&
    state.messagesStatus !== "loading"
  );
}

export function chatReducer(state: ChatUiState, action: ChatAction): ChatUiState {
  switch (action.type) {
    case "conversations/loading":
      return {
        ...state,
        conversationsStatus: "loading",
        conversationsError: null,
      };
    case "conversations/loaded":
      return {
        ...state,
        conversationsStatus: "ready",
        conversationsError: null,
        conversations: sortConversations(action.conversations),
      };
    case "conversations/error":
      return {
        ...state,
        conversationsStatus: "error",
        conversationsError: action.message,
      };
    case "conversation/created": {
      const conversations = sortConversations([
        action.conversation,
        ...state.conversations.filter((c) => c.id !== action.conversation.id),
      ]);
      return {
        ...state,
        conversations,
        conversationsStatus: "ready",
        conversationsError: null,
        activeConversationId: action.conversation.id,
        messages: [],
        messagesStatus: "ready",
        messagesError: null,
        banner: null,
      };
    }
    case "conversation/upsert": {
      const conversations = sortConversations([
        action.conversation,
        ...state.conversations.filter((c) => c.id !== action.conversation.id),
      ]);
      return { ...state, conversations };
    }
    case "conversation/select":
      if (action.conversationId === state.activeConversationId) {
        return state;
      }
      return {
        ...state,
        activeConversationId: action.conversationId,
        messages: [],
        messagesStatus: action.conversationId ? "loading" : "idle",
        messagesError: null,
        banner: null,
        streamPhase: "idle",
        activeRunId: null,
        streamingMessageId: null,
      };
    case "messages/loading":
      if (action.conversationId !== state.activeConversationId) return state;
      return {
        ...state,
        messagesStatus: "loading",
        messagesError: null,
      };
    case "messages/loaded": {
      if (action.conversationId !== state.activeConversationId) return state;
      // Preserve only the in-flight assistant bubble; persisted history already
      // contains the user turn after claim, so local-user-* must not duplicate it.
      const streamingLocals = state.messages.filter(
        (m) =>
          m.role === "assistant" &&
          (m.status === "streaming" || m.id === state.streamingMessageId),
      );
      return {
        ...state,
        messagesStatus: "ready",
        messagesError: null,
        messages: mergeMessagesById(action.messages, streamingLocals),
      };
    }
    case "messages/error":
      if (action.conversationId !== state.activeConversationId) return state;
      return {
        ...state,
        messagesStatus: "error",
        messagesError: action.message,
      };
    case "banner/set":
      return { ...state, banner: action.banner };
    case "banner/clear":
      return { ...state, banner: null };
    case "send/begin": {
      if (!canSend(state) || state.activeConversationId !== action.conversationId) {
        return state;
      }
      const now = new Date().toISOString();
      const nextSeq = state.localSeq + 1;
      const userMessage: ChatMessage = {
        id: action.tempUserId,
        conversation_id: action.conversationId,
        owner_email: "",
        role: "user",
        status: "complete",
        content_text: action.content,
        provider: null,
        model: null,
        sequence: nextSeq * 2 - 1,
        error_code: null,
        error_message: null,
        created_at: now,
        updated_at: now,
        completed_at: now,
      };
      const assistantMessage: ChatMessage = {
        id: action.tempAssistantId,
        conversation_id: action.conversationId,
        owner_email: "",
        role: "assistant",
        status: "streaming",
        content_text: "",
        provider: "mock",
        model: "mock-echo-v1",
        sequence: nextSeq * 2,
        error_code: null,
        error_message: null,
        created_at: now,
        updated_at: now,
        completed_at: null,
      };
      return {
        ...state,
        localSeq: nextSeq,
        streamPhase: "sending",
        activeRunId: null,
        streamingMessageId: action.tempAssistantId,
        banner: null,
        messages: [...state.messages, userMessage, assistantMessage],
      };
    }
    case "send/stream-event":
      return applyStreamEvent(state, action.event);
    case "send/http-error": {
      const messages = removeOptimisticStreamingPair(state);
      const banner = bannerForHttpError(action.status, action.code, action.message);
      return {
        ...state,
        messages,
        streamPhase: "idle",
        activeRunId: null,
        streamingMessageId: null,
        banner,
      };
    }
    case "send/stop-requested":
      if (state.streamPhase !== "sending" && state.streamPhase !== "streaming") {
        return state;
      }
      return { ...state, streamPhase: "stopping" };
    case "send/finished": {
      const messages = state.messages.map((message) => {
        if (message.id !== state.streamingMessageId) return message;
        if (message.status !== "streaming") return message;
        if (action.outcome === "aborted") {
          return {
            ...message,
            status: "partial",
            error_code: message.error_code ?? "cancelled",
            error_message: message.error_message ?? "Interrupted",
            completed_at: message.completed_at ?? new Date().toISOString(),
          };
        }
        if (action.outcome === "interrupted" || action.outcome === "failed") {
          return {
            ...message,
            status: action.outcome === "failed" ? "failed" : "partial",
            error_code: message.error_code ?? "interrupted",
            error_message:
              message.error_message ??
              (action.outcome === "failed"
                ? "Response failed"
                : "Stream interrupted"),
            completed_at: message.completed_at ?? new Date().toISOString(),
          };
        }
        return {
          ...message,
          status: "complete",
          completed_at: message.completed_at ?? new Date().toISOString(),
        };
      });
      return {
        ...state,
        messages,
        streamPhase: "idle" as StreamPhase,
        activeRunId: null,
        streamingMessageId: null,
      };
    }
    case "history/reconcile":
      return {
        ...state,
        messages: mergeMessagesById(action.messages, []),
        messagesStatus: "ready",
        messagesError: null,
      };
    default:
      return state;
  }
}

function applyStreamEvent(state: ChatUiState, event: ParsedSseEvent): ChatUiState {
  switch (event.event) {
    case "message_start": {
      const runId = event.data.run_id;
      const messageId = event.data.message_id;
      const messages: ChatMessage[] = state.messages.map((message) => {
        if (message.id !== state.streamingMessageId) return message;
        return {
          ...message,
          id: messageId || message.id,
          status: "streaming",
        };
      });
      return {
        ...state,
        streamPhase: "streaming",
        activeRunId: runId || state.activeRunId,
        streamingMessageId: messageId || state.streamingMessageId,
        messages,
      };
    }
    case "content_delta": {
      const messageId = event.data.message_id;
      const delta = event.data.delta;
      const targetId = messageId || state.streamingMessageId;
      const messages: ChatMessage[] = state.messages.map((message) => {
        if (message.id !== targetId) return message;
        return {
          ...message,
          content_text: `${message.content_text}${delta}`,
          status: "streaming",
          updated_at: new Date().toISOString(),
        };
      });
      return {
        ...state,
        streamPhase: state.streamPhase === "stopping" ? "stopping" : "streaming",
        streamingMessageId: targetId,
        messages,
      };
    }
    case "message_end": {
      const messageId = event.data.message_id;
      const endStatus = event.data.status || "complete";
      const targetId = messageId || state.streamingMessageId;
      const messages: ChatMessage[] = state.messages.map((message) => {
        if (message.id !== targetId) return message;
        return {
          ...message,
          status: endStatus,
          completed_at: new Date().toISOString(),
          error_code: null,
          error_message: null,
        };
      });
      return {
        ...state,
        messages,
        streamPhase: "idle",
        activeRunId: null,
        streamingMessageId: null,
      };
    }
    case "error": {
      const messageId = event.data.message_id;
      const code = event.data.code;
      const errorMessage = event.data.message;
      const partial = Boolean(event.data.partial);
      const targetId = messageId || state.streamingMessageId;
      const messages: ChatMessage[] = state.messages.map((msg) => {
        if (msg.id !== targetId) return msg;
        return {
          ...msg,
          status: partial ? "partial" : "failed",
          error_code: code,
          error_message: errorMessage,
          completed_at: new Date().toISOString(),
        };
      });
      return {
        ...state,
        messages,
        streamPhase: "idle",
        activeRunId: null,
        streamingMessageId: null,
        banner: {
          kind: "error",
          code,
          message: errorMessage,
          retryable: code !== "run_in_progress",
        },
      };
    }
    default:
      return state;
  }
}

function removeOptimisticStreamingPair(state: ChatUiState): ChatMessage[] {
  if (!state.streamingMessageId) return state.messages;
  const assistantId = state.streamingMessageId;
  // Drop the trailing optimistic assistant (and its paired local user if still local-*).
  const withoutAssistant = state.messages.filter((m) => m.id !== assistantId);
  const last = withoutAssistant[withoutAssistant.length - 1];
  if (last && last.role === "user" && last.id.startsWith("local-user-")) {
    return withoutAssistant.slice(0, -1);
  }
  return withoutAssistant;
}

export function bannerForHttpError(
  status: number,
  code: string,
  message: string,
): ChatBanner {
  if (status === 409 || code === "run_in_progress") {
    return {
      kind: "info",
      code: "run_in_progress",
      message: message || "Reply already in progress",
    };
  }
  if (status === 0 || code === "network_error") {
    return {
      kind: "error",
      code: "network_error",
      message: message || "Network failure. Check your connection and try again.",
      retryable: true,
    };
  }
  return {
    kind: "error",
    code,
    message: message || "Unable to send message",
    retryable: true,
  };
}

export function makeTempIds(localSeq: number): {
  tempUserId: string;
  tempAssistantId: string;
} {
  const n = localSeq + 1;
  return {
    tempUserId: `local-user-${n}`,
    tempAssistantId: `local-assistant-${n}`,
  };
}
