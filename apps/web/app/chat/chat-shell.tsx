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

  const abortRef = useRef<AbortController | null>(null);
  const sendLockRef = useRef(false);
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
      abortRef.current?.abort();
      sendLockRef.current = false;
    };
  }, []);

  function navigateToConversation(conversationId: string | null) {
    if (
      conversationId !== activeIdRef.current &&
      (state.streamPhase === "sending" ||
        state.streamPhase === "streaming" ||
        state.streamPhase === "stopping")
    ) {
      abortRef.current?.abort();
      sendLockRef.current = false;
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
    if (creating || sendLockRef.current) return;
    setCreating(true);
    try {
      const conversation = await createConversation();
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
    if (!conversationId || !canSend(state) || sendLockRef.current) return;

    sendLockRef.current = true;
    const { tempUserId, tempAssistantId } = makeTempIds(state.localSeq);
    dispatch({
      type: "send/begin",
      conversationId,
      content,
      tempUserId,
      tempAssistantId,
    });

    const controller = new AbortController();
    abortRef.current = controller;

    const result = await sendMessageStream({
      conversationId,
      content,
      signal: controller.signal,
      onEvent: (event) => {
        dispatch({ type: "send/stream-event", event });
      },
    });

    if (!result.ok) {
      dispatch({
        type: "send/http-error",
        status: result.error.status,
        code: result.error.code,
        message: result.error.message,
      });
      // For 409, refresh history in case another run already appended turns.
      if (result.error.status === 409 || result.error.code === "run_in_progress") {
        void loadMessages(conversationId);
      }
      sendLockRef.current = false;
      abortRef.current = null;
      return;
    }

    dispatch({ type: "send/finished", outcome: result.outcome });

    // Reconcile with persisted history (titles, real ids, terminal statuses).
    try {
      const [messages, conversations] = await Promise.all([
        listMessages(conversationId),
        listConversations(),
      ]);
      if (activeIdRef.current === conversationId) {
        dispatch({ type: "history/reconcile", messages });
      }
      dispatch({ type: "conversations/loaded", conversations });
    } catch {
      // Soft failure — streamed content already visible.
    }

    sendLockRef.current = false;
    abortRef.current = null;
  }

  async function handleStop() {
    if (state.streamPhase !== "sending" && state.streamPhase !== "streaming") {
      return;
    }
    dispatch({ type: "send/stop-requested" });
    const runId = state.activeRunId;
    if (runId) {
      try {
        await cancelRun(runId);
      } catch {
        // Disconnect abort still finalizes partial on the server.
      }
    }
    abortRef.current?.abort();
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
              onClick={() => {
                setMobilePane("list");
                startTransition(() => router.push("/chat"));
              }}
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
