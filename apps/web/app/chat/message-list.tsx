"use client";

import { useEffect, useRef } from "react";

import type { ChatMessage, StreamPhase } from "./chat-types";

type MessageListProps = {
  messages: ChatMessage[];
  status: "idle" | "loading" | "ready" | "error";
  error: string | null;
  streamPhase: StreamPhase;
  emptyHint?: string;
  onRetryLoad?: () => void;
};

function statusLabel(message: ChatMessage, streamPhase: StreamPhase): string | null {
  if (message.role !== "assistant") return null;
  if (message.status === "streaming") {
    return streamPhase === "stopping" ? "Stopping…" : "Generating…";
  }
  if (message.status === "partial") return "Interrupted";
  if (message.status === "failed") {
    return message.error_message || "Failed";
  }
  return null;
}

export function MessageList({
  messages,
  status,
  error,
  streamPhase,
  emptyHint = "Send a message to start the conversation.",
  onRetryLoad,
}: MessageListProps) {
  const endRef = useRef<HTMLDivElement | null>(null);
  const scrollerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const node = endRef.current;
    if (!node) return;
    node.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [messages, streamPhase]);

  if (status === "loading") {
    return (
      <div className="chat-transcript" role="status">
        <p className="muted">Loading messages…</p>
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className="chat-transcript" role="alert">
        <p className="muted">{error ?? "Unable to load messages."}</p>
        {onRetryLoad ? (
          <button type="button" className="chat-text-button" onClick={onRetryLoad}>
            Retry
          </button>
        ) : null}
      </div>
    );
  }

  if (messages.length === 0) {
    return (
      <div className="chat-transcript chat-transcript-empty">
        <p className="muted">{emptyHint}</p>
      </div>
    );
  }

  return (
    <div
      className="chat-transcript"
      ref={scrollerRef}
      aria-live="polite"
      aria-relevant="additions text"
    >
      <ol className="chat-message-list">
        {messages
          .filter((message) => message.role === "user" || message.role === "assistant")
          .map((message) => {
            const label = statusLabel(message, streamPhase);
            const isUser = message.role === "user";
            return (
              <li
                key={message.id}
                className={
                  isUser ? "chat-message chat-message-user" : "chat-message chat-message-assistant"
                }
              >
                <div className="chat-message-role">
                  {isUser ? "You" : "Assistant"}
                  {label ? <span className="chat-message-status">{label}</span> : null}
                </div>
                <div className="chat-message-body">
                  {message.content_text ||
                    (message.status === "streaming" ? (
                      <span className="chat-streaming-cursor" aria-hidden="true">
                        ▍
                      </span>
                    ) : (
                      ""
                    ))}
                  {message.status === "streaming" && message.content_text ? (
                    <span className="chat-streaming-cursor" aria-hidden="true">
                      ▍
                    </span>
                  ) : null}
                </div>
                {message.status === "failed" && message.error_message ? (
                  <p className="chat-message-error">{message.error_message}</p>
                ) : null}
                {message.status === "partial" ? (
                  <p className="chat-message-partial muted">
                    {message.error_message || "Response interrupted."}
                  </p>
                ) : null}
              </li>
            );
          })}
      </ol>
      <div ref={endRef} />
    </div>
  );
}
