/**
 * Browser client for authenticated chat BFF routes (never calls FastAPI).
 */

import type {
  ChatErrorDetail,
  ChatMessage,
  Conversation,
  ParsedSseEvent,
} from "./chat-types";
import { consumeSseStream } from "./chat-sse";

export class ChatApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail: ChatErrorDetail | null;

  constructor(status: number, code: string, message: string, detail: ChatErrorDetail | null = null) {
    super(message);
    this.name = "ChatApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

function detailFromBody(body: unknown): ChatErrorDetail | null {
  if (!body || typeof body !== "object") return null;
  const record = body as Record<string, unknown>;
  const detail = record.detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const d = detail as Record<string, unknown>;
    if (typeof d.code === "string" && typeof d.message === "string") {
      return {
        code: d.code,
        message: d.message,
        detail:
          d.detail && typeof d.detail === "object"
            ? (d.detail as Record<string, unknown>)
            : null,
      };
    }
  }
  if (typeof record.code === "string" && typeof record.message === "string") {
    return {
      code: record.code,
      message: record.message,
    };
  }
  return null;
}

async function parseJsonResponse(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return { raw: text };
  }
}

async function expectOkJson<T>(response: Response): Promise<T> {
  const body = await parseJsonResponse(response);
  if (!response.ok) {
    const detail = detailFromBody(body);
    throw new ChatApiError(
      response.status,
      detail?.code ?? `http_${response.status}`,
      detail?.message ?? `Request failed (${response.status})`,
      detail,
    );
  }
  return body as T;
}

export async function listConversations(
  init?: { signal?: AbortSignal; limit?: number },
): Promise<Conversation[]> {
  const qs =
    init?.limit !== undefined ? `?limit=${encodeURIComponent(String(init.limit))}` : "";
  const response = await fetch(`/api/chat/conversations${qs}`, {
    method: "GET",
    credentials: "same-origin",
    cache: "no-store",
    signal: init?.signal,
  });
  return expectOkJson<Conversation[]>(response);
}

export async function createConversation(
  input: { title?: string | null } = {},
  init?: { signal?: AbortSignal },
): Promise<Conversation> {
  const response = await fetch("/api/chat/conversations", {
    method: "POST",
    credentials: "same-origin",
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: input.title ?? null,
      default_provider: "mock",
      default_model: "mock-echo-v1",
    }),
    signal: init?.signal,
  });
  return expectOkJson<Conversation>(response);
}

export async function listMessages(
  conversationId: string,
  init?: { signal?: AbortSignal; limit?: number },
): Promise<ChatMessage[]> {
  const qs =
    init?.limit !== undefined ? `?limit=${encodeURIComponent(String(init.limit))}` : "";
  const response = await fetch(
    `/api/chat/conversations/${encodeURIComponent(conversationId)}/messages${qs}`,
    {
      method: "GET",
      credentials: "same-origin",
      cache: "no-store",
      signal: init?.signal,
    },
  );
  return expectOkJson<ChatMessage[]>(response);
}

export type SendMessageResult =
  | { ok: true; outcome: "completed" | "aborted" | "interrupted" }
  | { ok: false; error: ChatApiError };

/**
 * POST a user message and consume the SSE assistant stream via the BFF.
 * Does not accept or send owner_email — the BFF derives it from the session.
 */
export async function sendMessageStream(options: {
  conversationId: string;
  content: string;
  signal: AbortSignal;
  onEvent: (event: ParsedSseEvent) => void;
}): Promise<SendMessageResult> {
  let response: Response;
  try {
    response = await fetch(
      `/api/chat/conversations/${encodeURIComponent(options.conversationId)}/messages`,
      {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body: JSON.stringify({ content: options.content }),
        signal: options.signal,
      },
    );
  } catch {
    if (options.signal.aborted) {
      return { ok: true, outcome: "aborted" };
    }
    return {
      ok: false,
      error: new ChatApiError(
        0,
        "network_error",
        "Network failure while sending message",
      ),
    };
  }

  if (!response.ok) {
    const body = await parseJsonResponse(response);
    const detail = detailFromBody(body);
    return {
      ok: false,
      error: new ChatApiError(
        response.status,
        detail?.code ?? `http_${response.status}`,
        detail?.message ?? `Request failed (${response.status})`,
        detail,
      ),
    };
  }

  if (!response.body) {
    return {
      ok: false,
      error: new ChatApiError(502, "empty_stream", "No stream body from chat proxy"),
    };
  }

  const outcome = await consumeSseStream(
    response.body,
    options.onEvent,
    options.signal,
  );
  return { ok: true, outcome };
}

export async function cancelRun(
  runId: string,
  init?: { signal?: AbortSignal },
): Promise<void> {
  const response = await fetch(
    `/api/chat/runs/${encodeURIComponent(runId)}/cancel`,
    {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
      signal: init?.signal,
    },
  );
  await expectOkJson(response);
}

/** Merge persisted history with in-flight optimistic rows without duplicates. */
export function mergeMessagesById(
  persisted: ChatMessage[],
  local: ChatMessage[],
): ChatMessage[] {
  const byId = new Map<string, ChatMessage>();
  for (const message of [...persisted, ...local]) {
    const existing = byId.get(message.id);
    if (!existing) {
      byId.set(message.id, message);
      continue;
    }
    // Prefer the richer / more terminal status when ids collide.
    const preferPersisted =
      statusRank(message.status) >= statusRank(existing.status) &&
      message.content_text.length >= existing.content_text.length;
    byId.set(message.id, preferPersisted ? message : existing);
  }
  return [...byId.values()].sort((a, b) => {
    if (a.sequence !== b.sequence) return a.sequence - b.sequence;
    return a.created_at.localeCompare(b.created_at);
  });
}

function statusRank(status: string): number {
  switch (status) {
    case "complete":
      return 4;
    case "partial":
      return 3;
    case "failed":
      return 3;
    case "streaming":
      return 2;
    default:
      return 1;
  }
}

export function sortConversations(conversations: Conversation[]): Conversation[] {
  return [...conversations].sort((a, b) =>
    b.updated_at.localeCompare(a.updated_at),
  );
}
