"use client";

import {
  useEffect,
  useRef,
  type FormEvent,
  type KeyboardEvent,
} from "react";

import type { StreamPhase } from "./chat-types";

type MessageComposerProps = {
  disabled: boolean;
  streamPhase: StreamPhase;
  onSend: (content: string) => void;
  onStop: () => void;
  autoFocus?: boolean;
};

function isCoarsePointer(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false;
  }
  return window.matchMedia("(pointer: coarse)").matches;
}

export function MessageComposer({
  disabled,
  streamPhase,
  onSend,
  onStop,
  autoFocus = true,
}: MessageComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const busy =
    streamPhase === "sending" ||
    streamPhase === "streaming" ||
    streamPhase === "stopping";

  useEffect(() => {
    if (autoFocus && !busy) {
      textareaRef.current?.focus();
    }
  }, [autoFocus, busy]);

  function resize() {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }

  function submit() {
    const el = textareaRef.current;
    if (!el || disabled || busy) return;
    const content = el.value.trim();
    if (!content) return;
    onSend(content);
    el.value = "";
    resize();
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    submit();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // Desktop: Enter sends, Shift+Enter newline.
    // Mobile/coarse pointer: Enter inserts newline; use the Send button.
    if (event.key !== "Enter") return;
    if (event.nativeEvent.isComposing) return;
    if (isCoarsePointer()) return;
    if (event.shiftKey) return;
    event.preventDefault();
    submit();
  }

  return (
    <form className="chat-composer" onSubmit={handleSubmit}>
      <label className="visually-hidden" htmlFor="chat-composer-input">
        Message
      </label>
      <textarea
        id="chat-composer-input"
        ref={textareaRef}
        className="chat-composer-input"
        rows={1}
        placeholder={busy ? "Waiting for reply…" : "Message Personal Command Center…"}
        disabled={disabled || busy}
        onKeyDown={handleKeyDown}
        onInput={resize}
        enterKeyHint="send"
        autoComplete="off"
      />
      <div className="chat-composer-actions">
        {busy ? (
          <button
            type="button"
            className="chat-stop-button"
            onClick={onStop}
            disabled={streamPhase === "stopping"}
          >
            {streamPhase === "stopping" ? "Stopping…" : "Stop"}
          </button>
        ) : (
          <button
            type="submit"
            className="chat-send-button"
            disabled={disabled}
          >
            Send
          </button>
        )}
      </div>
    </form>
  );
}
