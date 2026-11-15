/**
 * Incremental SSE parser for chat streams (PR4 BFF → browser).
 * Pure module — no React / Auth.js imports.
 */

import type { ParsedSseEvent } from "./chat-types";

function parseDataLine(raw: string): Record<string, unknown> {
  const trimmed = raw.trim();
  if (!trimmed) return {};
  try {
    const parsed: unknown = JSON.parse(trimmed);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
    return { value: parsed };
  } catch {
    return { raw: trimmed };
  }
}

/**
 * Parse a complete SSE block (event + data lines joined by newlines).
 */
export function parseSseBlock(block: string): ParsedSseEvent | null {
  const lines = block.split(/\r?\n/);
  let eventName = "message";
  const dataLines: string[] = [];

  for (const line of lines) {
    if (!line || line.startsWith(":")) continue;
    if (line.startsWith("event:")) {
      eventName = line.slice("event:".length).trim() || "message";
      continue;
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trimStart());
    }
  }

  if (dataLines.length === 0) return null;
  const data = parseDataLine(dataLines.join("\n"));

  switch (eventName) {
    case "message_start":
      return {
        event: "message_start",
        data: {
          run_id: String(data.run_id ?? ""),
          message_id: String(data.message_id ?? ""),
          role: typeof data.role === "string" ? data.role : undefined,
        },
      };
    case "content_delta":
      return {
        event: "content_delta",
        data: {
          message_id: String(data.message_id ?? ""),
          delta: String(data.delta ?? ""),
        },
      };
    case "usage":
      return {
        event: "usage",
        data: {
          message_id: String(data.message_id ?? ""),
          input_tokens:
            typeof data.input_tokens === "number" ? data.input_tokens : null,
          output_tokens:
            typeof data.output_tokens === "number" ? data.output_tokens : null,
        },
      };
    case "message_end":
      return {
        event: "message_end",
        data: {
          message_id: String(data.message_id ?? ""),
          status: String(data.status ?? "complete"),
          finish_reason:
            data.finish_reason === undefined || data.finish_reason === null
              ? null
              : String(data.finish_reason),
        },
      };
    case "error":
      return {
        event: "error",
        data: {
          message_id:
            data.message_id === undefined || data.message_id === null
              ? null
              : String(data.message_id),
          code: String(data.code ?? "stream_error"),
          message: String(data.message ?? "Stream error"),
          partial: Boolean(data.partial),
        },
      };
    default:
      return { event: "unknown", data, rawEvent: eventName };
  }
}

/**
 * Feed raw SSE text chunks; yields complete parsed events as blocks arrive.
 */
export function createSseParser(): {
  push: (chunk: string) => ParsedSseEvent[];
  flush: () => ParsedSseEvent[];
} {
  let buffer = "";

  function drain(final: boolean): ParsedSseEvent[] {
    const events: ParsedSseEvent[] = [];
    // SSE blocks are separated by a blank line.
    while (true) {
      const match = buffer.match(/\r?\n\r?\n/);
      if (!match || match.index === undefined) break;
      const block = buffer.slice(0, match.index);
      buffer = buffer.slice(match.index + match[0].length);
      const parsed = parseSseBlock(block);
      if (parsed) events.push(parsed);
    }
    if (final && buffer.trim()) {
      const parsed = parseSseBlock(buffer);
      buffer = "";
      if (parsed) events.push(parsed);
    }
    return events;
  }

  return {
    push(chunk: string) {
      buffer += chunk;
      return drain(false);
    },
    flush() {
      return drain(true);
    },
  };
}

/**
 * Read a fetch body as SSE events, invoking onEvent for each.
 * Stops when the stream ends or signal aborts.
 */
export async function consumeSseStream(
  body: ReadableStream<Uint8Array>,
  onEvent: (event: ParsedSseEvent) => void,
  signal?: AbortSignal,
): Promise<"completed" | "aborted" | "interrupted"> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  const parser = createSseParser();
  let sawTerminal = false;

  const onAbort = () => {
    void reader.cancel("aborted");
  };
  if (signal) {
    if (signal.aborted) {
      onAbort();
      return "aborted";
    }
    signal.addEventListener("abort", onAbort, { once: true });
  }

  try {
    while (true) {
      if (signal?.aborted) return "aborted";
      const { done, value } = await reader.read();
      if (done) break;
      const text = decoder.decode(value, { stream: true });
      for (const event of parser.push(text)) {
        onEvent(event);
        if (event.event === "message_end" || event.event === "error") {
          sawTerminal = true;
        }
      }
    }
    for (const event of parser.flush()) {
      onEvent(event);
      if (event.event === "message_end" || event.event === "error") {
        sawTerminal = true;
      }
    }
    return sawTerminal ? "completed" : "interrupted";
  } catch {
    if (signal?.aborted) return "aborted";
    return "interrupted";
  } finally {
    if (signal) {
      signal.removeEventListener("abort", onAbort);
    }
    try {
      reader.releaseLock();
    } catch {
      // ignore
    }
  }
}
