"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  useCallback,
  useEffect,
  useReducer,
  useRef,
  useState,
  useTransition,
} from "react";

import { SignOutButton } from "../sign-out-button";
import {
  cancelRun,
  createConversation,
  listConversations,
  listMessages,
  sendMessageStream,
} from "./chat-client";
import { ConversationList } from "./conversation-list";
import { MessageComposer } from "./message-composer";
import { MessageList } from "./message-list";
import {
  canSend,
  chatReducer,
  createInitialChatState,
  makeTempIds,
} from "./chat-state";
import type { Conversation } from "./chat-types";

type ChatShellProps = {
  email: string;
  signOutAction: () => Promise<void>;
  initialConversationId: string | null;
  initialConversations?: Conversation[];
};

type ActiveSend = {
  streamId: string;
  conversationId: string;
  controller: AbortController;
};

export function ChatShell({
  email,
  signOutAction,
  initialConversationId,
  initialConversations = [],
}: ChatShellProps) {
  const router = useRouter();
  const [, startTransition] = useTransition();
  const [state, dispatch] = useReducer(
    chatReducer,
    createInitialChatState({
      conversations: initialConversations,
      conversationsStatus: "ready",
      activeConversationId: initialConversationId,
      messagesStatus: initialConversationId ? "loading" : "idle",
    }),
  );
  const [creating, setCreating] = useState(false);
  const [mobilePane, setMobilePane] = useState<"list" | "thread">(
    initialConversationId ? "thread" : "list",
  );

  const activeSendRef = useRef<ActiveSend | null>(null);
  const streamSeqRef = useRef(0);
  const activeIdRef = useRef(state.activeConversationId);
  activeIdRef.current = state.activeConversationId;

  const refreshConversations = useCallback(async () => {
    dispatch({ type: "conversations/loading" });
    try {
      const conversations = await listConversations();
      dispatch({ type: "conversations/loaded", conversations });
    } catch (error) {
      dispatch({
        type: "conversations/error",
        message:
          error instanceof Error
            ? error.message
            : "Unable to load conversations.",
      });
    }
  }, []);

  const loadMessages = useCallback(async (conversationId: string) => {
    dispatch({ type: "messages/loading", conversationId });
    try {
      const messages = await listMessages(conversationId);
      if (activeIdRef.current !== conversationId) return;
      dispatch({ type: "messages/loaded", conversationId, messages });
    } catch (error) {
      if (activeIdRef.current !== conversationId) return;
      dispatch({
        type: "messages/error",
        conversationId,
        message:
          error instanceof Error ? error.message : "Unable to load messages.",
      });
    }
  }, []);

  useEffect(() => {
    if (initialConversations.length === 0) {
      void refreshConversations();
    }
  }, [initialConversations.length, refreshConversations]);

  useEffect(() => {
    if (!state.activeConversationId) return;
    void loadMessages(state.activeConversationId);
  }, [state.activeConversationId, loadMessages]);

  useEffect(() => {
    return () => {
      activeSendRef.current?.controller.abort();
      activeSendRef.current = null;
    };
  }, []);

  function invalidateActiveSend() {
    const current = activeSendRef.current;
    if (!current) return;
    current.controller.abort();
    activeSendRef.current = null;
  }

  function navigateToConversation(conversationId: string | null) {
    if (conversationId !== activeIdRef.current) {
      invalidateActiveSend();
    }
    dispatch({ type: "conversation/select", conversationId });
    setMobilePane(conversationId ? "thread" : "list");
    startTransition(() => {
      if (conversationId) {
        router.push(`/chat/${conversationId}`);
      } else {
        router.push("/chat");
      }
    });
  }

  async function handleCreate() {
    if (creating || activeSendRef.current) return;
    setCreating(true);
    try {
      const conversation = await createConversation();
      invalidateActiveSend();
      dispatch({ type: "conversation/created", conversation });
      setMobilePane("thread");
      startTransition(() => {
        router.push(`/chat/${conversation.id}`);
      });
    } catch (error) {
      dispatch({
        type: "banner/set",
        banner: {
          kind: "error",
          code: "create_failed",
          message:
            error instanceof Error
              ? error.message
              : "Unable to create conversation.",
          retryable: true,
        },
      });
    } finally {
      setCreating(false);
    }
  }

  async function handleSend(content: string) {
    const conversationId = state.activeConversationId;
    if (!conversationId || !canSend(state) || activeSendRef.current) return;

    streamSeqRef.current += 1;
    const streamId = `stream-${streamSeqRef.current}`;
    const { tempUserId, tempAssistantId } = makeTempIds(state.localSeq);
    dispatch({
      type: "send/begin",
      conversationId,
      streamId,
      content,
      tempUserId,
      tempAssistantId,
    });

    const controller = new AbortController();
    activeSendRef.current = { streamId, conversationId, controller };

    const result = await sendMessageStream({
      conversationId,
      content,
      signal: controller.signal,
      onEvent: (event) => {
        // Drop late chunks from an obsolete/aborted send.
        if (activeSendRef.current?.streamId !== streamId) return;
        dispatch({ type: "send/stream-event", streamId, event });
      },
    });

    // Stale completion after navigation or a newer send — do not touch UI/lock.
    if (activeSendRef.current?.streamId !== streamId) {
      return;
    }

    if (!result.ok) {
      dispatch({
        type: "send/http-error",
        streamId,
        status: result.error.status,
        code: result.error.code,
        message: result.error.message,
      });
      // For 409, refresh history in case another run already appended turns.
      if (
        result.error.status === 409 ||
        result.error.code === "run_in_progress"
      ) {
        if (activeIdRef.current === conversationId) {
          void loadMessages(conversationId);
        }
      }
      if (activeSendRef.current?.streamId === streamId) {
        activeSendRef.current = null;
      }
      return;
    }

    dispatch({ type: "send/finished", streamId, outcome: result.outcome });

    // Reconcile with persisted history (titles, real ids, terminal statuses).
    try {
      const [messages, conversations] = await Promise.all([
        listMessages(conversationId),
        listConversations(),
      ]);
      if (
        activeSendRef.current?.streamId === streamId ||
        activeIdRef.current === conversationId
      ) {
        if (activeIdRef.current === conversationId) {
          dispatch({
            type: "history/reconcile",
            conversationId,
            messages,
          });
        }
      }
      dispatch({ type: "conversations/loaded", conversations });
    } catch {
      // Soft failure — streamed content already visible.
    }

    if (activeSendRef.current?.streamId === streamId) {
      activeSendRef.current = null;
    }
  }

  async function handleStop() {
    const active = activeSendRef.current;
    if (!active) return;
    if (state.streamPhase !== "sending" && state.streamPhase !== "streaming") {
      return;
    }
    dispatch({ type: "send/stop-requested", streamId: active.streamId });
    const runId = state.activeRunId;
    if (runId) {
      try {
        await cancelRun(runId);
      } catch {
        // Disconnect abort still finalizes partial on the server.
      }
    }
    active.controller.abort();
  }

  const activeConversation =
    state.conversations.find((c) => c.id === state.activeConversationId) ??
    null;
  const composerDisabled =
    !state.activeConversationId || state.messagesStatus === "loading";
  const showThread = Boolean(state.activeConversationId);

  return (
    <div className="chat-app">
      <header className="chat-top-bar">
        <div className="chat-top-bar-brand">
          <p className="eyebrow">PERSONAL COMMAND CENTER · V0.1</p>
          <p className="chat-top-title">Chat</p>
        </div>
        <div className="session-meta">
          <Link href="/">Inbox</Link>
          <Link href="/settings/api-tokens">API tokens</Link>
          <span className="muted">{email}</span>
          <SignOutButton signOutAction={signOutAction} />
        </div>
      </header>

      <div
        className={
          mobilePane === "thread" && showThread
            ? "chat-shell show-thread"
            : "chat-shell show-list"
        }
      >
        <aside className="chat-pane chat-pane-list" aria-label="Conversation list">
          <ConversationList
            conversations={state.conversations}
            activeConversationId={state.activeConversationId}
            status={state.conversationsStatus}
            error={state.conversationsError}
            creating={creating}
            onSelect={(id) => navigateToConversation(id)}
            onCreate={() => {
              void handleCreate();
            }}
            onRetry={() => {
              void refreshConversations();
            }}
          />
        </aside>

        <section className="chat-pane chat-pane-thread" aria-label="Conversation">
          <div className="chat-thread-header">
            <button
              type="button"
              className="chat-back-button"
              onClick={() => navigateToConversation(null)}
            >
              Conversations
            </button>
            <div className="chat-thread-heading">
              <h1 className="chat-thread-title">
                {activeConversation?.title?.trim() ||
                  (showThread ? "Conversation" : "Chat")}
              </h1>
              {activeConversation ? (
                <p className="muted chat-model-label">
                  {activeConversation.default_model}
                </p>
              ) : null}
            </div>
          </div>

          {state.banner ? (
            <div
              className={
                state.banner.kind === "info"
                  ? "chat-banner chat-banner-info"
                  : "chat-banner chat-banner-error"
              }
              role={state.banner.kind === "error" ? "alert" : "status"}
            >
              <p>{state.banner.message}</p>
              <button
                type="button"
                className="chat-text-button"
                onClick={() => dispatch({ type: "banner/clear" })}
              >
                Dismiss
              </button>
            </div>
          ) : null}

          {!showThread ? (
            <div className="chat-empty-hero">
              <p className="muted">
                Select a conversation or start a new chat.
              </p>
              <button
                type="button"
                className="chat-new-button"
                onClick={() => {
                  void handleCreate();
                }}
                disabled={creating}
              >
                {creating ? "Creating…" : "New chat"}
              </button>
            </div>
          ) : (
            <>
              <MessageList
                messages={state.messages}
                status={state.messagesStatus}
                error={state.messagesError}
                streamPhase={state.streamPhase}
                onRetryLoad={() => {
                  if (state.activeConversationId) {
                    void loadMessages(state.activeConversationId);
                  }
                }}
              />
              <div className="chat-composer-dock">
                <MessageComposer
                  disabled={composerDisabled}
                  streamPhase={state.streamPhase}
                  onSend={(content) => {
                    void handleSend(content);
                  }}
                  onStop={() => {
                    void handleStop();
                  }}
                />
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
