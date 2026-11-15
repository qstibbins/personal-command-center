"use client";

import type { Conversation } from "./chat-types";

type ConversationListProps = {
  conversations: Conversation[];
  activeConversationId: string | null;
  status: "idle" | "loading" | "ready" | "error";
  error: string | null;
  creating: boolean;
  onSelect: (conversationId: string) => void;
  onCreate: () => void;
  onRetry?: () => void;
};

function titleFor(conversation: Conversation): string {
  const title = conversation.title?.trim();
  return title || "New conversation";
}

export function ConversationList({
  conversations,
  activeConversationId,
  status,
  error,
  creating,
  onSelect,
  onCreate,
  onRetry,
}: ConversationListProps) {
  return (
    <div className="chat-sidebar">
      <div className="chat-sidebar-header">
        <h2 className="chat-sidebar-title">Conversations</h2>
        <button
          type="button"
          className="chat-new-button"
          onClick={onCreate}
          disabled={creating}
          aria-busy={creating || undefined}
        >
          {creating ? "Creating…" : "New chat"}
        </button>
      </div>

      {status === "loading" ? (
        <p className="muted chat-sidebar-status" role="status">
          Loading conversations…
        </p>
      ) : null}

      {status === "error" ? (
        <div className="chat-sidebar-status" role="alert">
          <p className="muted">{error ?? "Unable to load conversations."}</p>
          {onRetry ? (
            <button type="button" className="chat-text-button" onClick={onRetry}>
              Retry
            </button>
          ) : null}
        </div>
      ) : null}

      {status === "ready" && conversations.length === 0 ? (
        <div className="chat-sidebar-status">
          <p className="muted">No conversations yet.</p>
          <p className="muted">Start a new chat to begin.</p>
        </div>
      ) : null}

      {conversations.length > 0 ? (
        <ul className="chat-conversation-list" aria-label="Conversations">
          {conversations.map((conversation) => {
            const active = conversation.id === activeConversationId;
            return (
              <li key={conversation.id}>
                <button
                  type="button"
                  className={
                    active
                      ? "chat-conversation-item is-active"
                      : "chat-conversation-item"
                  }
                  aria-current={active ? "page" : undefined}
                  onClick={() => onSelect(conversation.id)}
                >
                  <span className="chat-conversation-item-title">
                    {titleFor(conversation)}
                  </span>
                  <span className="chat-conversation-item-meta muted">
                    {conversation.default_model}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}
