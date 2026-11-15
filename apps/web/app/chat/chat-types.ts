/** Shared chat UI types for Phase 1A.2 PR5 (browser ↔ BFF only). */

export type ConversationStatus = "active" | "archived" | "deleted";

export type MessageRole = "system" | "user" | "assistant" | "tool";

export type MessageStatus = "complete" | "streaming" | "partial" | "failed";

export type Conversation = {
  id: string;
  owner_email: string;
  title: string | null;
  status: string;
  default_provider: string;
  default_model: string;
  system_prompt: string | null;
  next_sequence: number;
  source: string;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
};

export type ChatMessage = {
  id: string;
  conversation_id: string;
  owner_email: string;
  role: MessageRole | string;
  status: MessageStatus | string;
  content_text: string;
  provider: string | null;
  model: string | null;
  sequence: number;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
};

export type ChatErrorDetail = {
  code: string;
  message: string;
  detail?: Record<string, unknown> | null;
};

export type ChatBanner =
  | { kind: "error"; code: string; message: string; retryable: boolean }
  | { kind: "info"; code: string; message: string };

export type StreamPhase = "idle" | "sending" | "streaming" | "stopping";

export type ChatUiState = {
  conversations: Conversation[];
  conversationsStatus: "idle" | "loading" | "ready" | "error";
  conversationsError: string | null;
  activeConversationId: string | null;
  messages: ChatMessage[];
  messagesStatus: "idle" | "loading" | "ready" | "error";
  messagesError: string | null;
  streamPhase: StreamPhase;
  activeRunId: string | null;
  streamingMessageId: string | null;
  /** Opaque id for the in-flight send; late events from older sends are ignored. */
  activeStreamId: string | null;
  /** Conversation that owns activeStreamId (may differ briefly during teardown). */
  activeStreamConversationId: string | null;
  banner: ChatBanner | null;
  /** Monotonic client seq for optimistic user rows before server ids arrive. */
  localSeq: number;
};

export type MessageStartEvent = {
  run_id: string;
  message_id: string;
  role?: string;
};

export type ContentDeltaEvent = {
  message_id: string;
  delta: string;
};

export type UsageEvent = {
  message_id: string;
  input_tokens?: number | null;
  output_tokens?: number | null;
};

export type MessageEndEvent = {
  message_id: string;
  status: string;
  finish_reason?: string | null;
};

export type StreamErrorEvent = {
  message_id?: string | null;
  code: string;
  message: string;
  partial?: boolean;
};

export type ParsedSseEvent =
  | { event: "message_start"; data: MessageStartEvent }
  | { event: "content_delta"; data: ContentDeltaEvent }
  | { event: "usage"; data: UsageEvent }
  | { event: "message_end"; data: MessageEndEvent }
  | { event: "error"; data: StreamErrorEvent }
  | { event: "unknown"; data: Record<string, unknown>; rawEvent: string };
