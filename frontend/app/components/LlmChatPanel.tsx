"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { InfoTip } from "./InfoTip";
import { Markdown } from "./Markdown";

type ChatQueueItem = {
  id: string;
  conversationId: string;
  content: string;
  status: "queued" | "running" | "done" | "failed" | string;
  createdAt?: string | null;
  startedAt?: string | null;
  finishedAt?: string | null;
  error?: string | null;
};

type ChatConversationSummary = {
  id: string;
  title: string;
  createdAt?: string | null;
  updatedAt?: string | null;
  messageCount: number;
  lastMessage?: string | null;
};

type ChatMessage = {
  role: "system" | "user" | "assistant" | string;
  content: string;
  createdAt?: string | null;
};

type ChatConversation = {
  id: string;
  title: string;
  createdAt?: string | null;
  updatedAt?: string | null;
  messages: ChatMessage[];
};

type ChatStatus = {
  enabled: boolean;
  loading: boolean;
  queue: {
    total: number;
    queued: number;
    running: number;
    done: number;
    failed: number;
    items: ChatQueueItem[];
    current: ChatQueueItem | null;
  };
  conversations: ChatConversationSummary[];
};

const POLL_MS = 5000;
const CHAT_HELP = `**LLM Chat**
Local model for quick analysis and summaries.

- Dashboard chat is beta; for the full local agent experience use \`make chat_agent\`.
- Enable loads the model on demand.
- Prompts are queued and processed in order.
- Conversations are stored locally on this machine.`;

function formatTimestamp(value?: string | null): string {
  if (!value) return "--";
  return value.replace("T", " ");
}

function queueTone(status: string): "ok" | "warn" | "neutral" | "beta" {
  if (status === "failed") return "warn";
  if (status === "running") return "beta";
  if (status === "done") return "ok";
  return "neutral";
}

function modelLabel(enabled: boolean, loading: boolean): { label: string; tone: "ok" | "warn" | "neutral" } {
  if (enabled) return { label: "Model loaded", tone: "ok" };
  if (loading) return { label: "Loading model", tone: "neutral" };
  return { label: "Model offline", tone: "warn" };
}

export function LlmChatPanel() {
  const [status, setStatus] = useState<ChatStatus | null>(null);
  const [loadingStatus, setLoadingStatus] = useState(false);
  const [statusError, setStatusError] = useState<string | null>(null);

  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  const [conversation, setConversation] = useState<ChatConversation | null>(null);
  const [loadingConversation, setLoadingConversation] = useState(false);

  const [messageDraft, setMessageDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [enabling, setEnabling] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const didAutoSelect = useRef(false);
  const [lastConversationId, setLastConversationId] = useState<string | null>(null);

  const refreshStatus = useCallback(async (silent = false) => {
    try {
      if (!silent) setLoadingStatus(true);
      setStatusError(null);
      const res = await fetch("/api/dashboard/llm_chat");
      const payload = (await res.json()) as ChatStatus;
      if (!res.ok) {
        const detail = (payload as unknown as { detail?: string })?.detail;
        throw new Error(detail ?? "Failed to load chat status");
      }
      setStatus(payload);
    } catch (err) {
      setStatusError(err instanceof Error ? err.message : "Failed to load chat status");
    } finally {
      if (!silent) setLoadingStatus(false);
    }
  }, []);

  const loadConversation = useCallback(async (conversationId: string) => {
    try {
      setActionError(null);
      setLoadingConversation(true);
      const res = await fetch(`/api/llm_chat/conversations/${encodeURIComponent(conversationId)}`);
      const payload = (await res.json()) as ChatConversation;
      if (!res.ok) {
        const detail = (payload as unknown as { detail?: string })?.detail;
        throw new Error(detail ?? "Failed to load conversation");
      }
      setConversation(payload);
    } catch (err) {
      setConversation(null);
      setActionError(err instanceof Error ? err.message : "Failed to load conversation");
    } finally {
      setLoadingConversation(false);
    }
  }, []);

  useEffect(() => {
    refreshStatus();
    const interval = setInterval(() => refreshStatus(true), POLL_MS);
    return () => clearInterval(interval);
  }, [refreshStatus]);

  useEffect(() => {
    if (didAutoSelect.current) return;
    if (status?.conversations?.length) {
      setSelectedConversationId(status.conversations[0].id);
      didAutoSelect.current = true;
    }
  }, [status]);

  useEffect(() => {
    if (!selectedConversationId) {
      setConversation(null);
      return;
    }
    if (status && !status.conversations.some((item) => item.id === selectedConversationId)) {
      setSelectedConversationId(null);
      return;
    }
  }, [status, selectedConversationId]);

  useEffect(() => {
    if (!status || !lastConversationId) return;
    if (!status.conversations.some((item) => item.id === lastConversationId)) {
      setLastConversationId(null);
    }
  }, [status, lastConversationId]);

  const selectedSummary = useMemo(() => {
    if (!status || !selectedConversationId) return null;
    return status.conversations.find((item) => item.id === selectedConversationId) ?? null;
  }, [status, selectedConversationId]);

  useEffect(() => {
    if (!selectedConversationId || !selectedSummary) return;
    if (conversation?.id === selectedConversationId && conversation?.updatedAt === selectedSummary.updatedAt) return;
    loadConversation(selectedConversationId);
  }, [selectedConversationId, selectedSummary?.updatedAt, loadConversation, conversation?.id, conversation?.updatedAt]);

  useEffect(() => {
    if (selectedConversationId) {
      setLastConversationId(selectedConversationId);
    }
  }, [selectedConversationId]);

  const handleEnable = async () => {
    try {
      setActionError(null);
      setEnabling(true);
      const res = await fetch("/api/llm_chat/enable", { method: "POST" });
      const payload = (await res.json()) as { enabled?: boolean; loading?: boolean; detail?: string };
      if (!res.ok) {
        throw new Error(payload.detail ?? "Failed to enable model");
      }
      setStatus((prev) => (prev ? { ...prev, enabled: !!payload.enabled, loading: !!payload.loading } : prev));
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to enable model");
    } finally {
      setEnabling(false);
      refreshStatus();
    }
  };

  const handleSend = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = messageDraft.trim();
    if (!trimmed) return;
    try {
      setActionError(null);
      setSending(true);
      const body = selectedConversationId ? { message: trimmed, conversationId: selectedConversationId } : { message: trimmed };
      const res = await fetch("/api/llm_chat/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });
      const payload = (await res.json()) as { conversationId?: string; detail?: string };
      if (!res.ok) {
        throw new Error(payload.detail ?? "Failed to queue message");
      }
      setMessageDraft("");
      if (!selectedConversationId && payload.conversationId) {
        setSelectedConversationId(payload.conversationId);
      }
      refreshStatus();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to queue message");
    } finally {
      setSending(false);
    }
  };

  const queue = status?.queue;
  const conversations = status?.conversations ?? [];
  const enabled = status?.enabled ?? false;
  const loading = status?.loading ?? false;
  const canSend = enabled || loading;
  const badge = status ? modelLabel(enabled, loading) : { label: "Model status unknown", tone: "neutral" };
  const queueSummary = queue
    ? `${queue.queued} queued / ${queue.running} running / ${queue.failed} failed`
    : "Queue unavailable";

  const pendingForSelected = useMemo(() => {
    if (!selectedConversationId || !queue?.items) return [];
    return queue.items.filter(
      (item) => item.conversationId === selectedConversationId && item.status !== "done" && item.status !== "failed"
    );
  }, [queue?.items, selectedConversationId]);

  return (
    <section className="card chatCard">
      <header className="cardHeader">
        <div className="chatHeader">
          <div className="chatHeaderTitle">
            <h2>LLM Chat</h2>
            <InfoTip label="About LLM chat" content={CHAT_HELP} />
            <span className="pill pill-beta">Beta</span>
          </div>
          <p className="muted tiny">
            Local agentic chat model (beta). Load on demand, queue prompts, and review past conversations. For the
            full local agent experience, use <code>make chat_agent</code>.
          </p>
        </div>
        <div className="rowActions">
          <button
            className="button buttonSmall"
            type="button"
            onClick={handleEnable}
            disabled={enabling || enabled || loading}
          >
            {enabled ? "Model ready" : loading || enabling ? "Loading..." : "Enable"}
          </button>
          <button className="button buttonSmall" type="button" onClick={refreshStatus} disabled={loadingStatus}>
            {loadingStatus ? "Refreshing..." : "Refresh"}
          </button>
        </div>
      </header>

      <div className="status-row">
        <span className={`pill pill-${badge.tone}`}>{badge.label}</span>
        {statusError ? <span className="pill pill-warn">{statusError}</span> : null}
      </div>

      {actionError ? <p className="muted tiny">Error: {actionError}</p> : null}

      <div className="chatLayout">
        <div className="chatPane">
        <div className="chatPaneHeader">
          <div>
            <p className="muted tiny">Conversation</p>
            <p className="chatTitle">{conversation?.title ?? selectedSummary?.title ?? "New chat"}</p>
            {selectedSummary?.updatedAt ? (
              <p className="muted tiny">Updated {formatTimestamp(selectedSummary.updatedAt)}</p>
            ) : null}
          </div>
          <div className="rowActions">
            {selectedConversationId ? null : lastConversationId ? (
              <button
                className="button buttonSmall"
                type="button"
                onClick={() => setSelectedConversationId(lastConversationId)}
              >
                Back to last chat
              </button>
            ) : null}
            <button
              className="button buttonSmall"
              type="button"
              onClick={() => {
                setSelectedConversationId(null);
                setConversation(null);
              }}
            >
              New chat
            </button>
          </div>
        </div>

          <div className="chatMessages scrollArea">
            {loadingConversation ? (
              <div className="skeleton" style={{ minHeight: 160 }} />
            ) : conversation?.messages?.length ? (
              conversation.messages.map((msg, idx) => {
                const content = msg.content ?? "";
                return (
                  <div key={`${msg.role}-${idx}`} className={`chatBubble chatBubble-${msg.role}`}>
                    <div className="chatBubbleMeta">
                      <span>{msg.role}</span>
                      <span>{formatTimestamp(msg.createdAt)}</span>
                    </div>
                    <Markdown content={content} className="markdown markdownChat" />
                  </div>
                );
              })
            ) : (
              <p className="muted tiny">No messages yet. Queue a prompt to begin.</p>
            )}
          </div>

          {pendingForSelected.length ? (
            <div className="chatPending">
              <p className="muted tiny">Pending prompts for this chat</p>
              <div className="list">
                {pendingForSelected.map((item) => (
                  <div key={item.id} className="row rowTight">
                    <div className={`dot dot-${queueTone(item.status)}`} />
                    <div className="rowMain">
                      <p className="rowTitle">{item.content}</p>
                      <p className="muted tiny">{item.status}</p>
                    </div>
                    <p className="rowDetail">{formatTimestamp(item.createdAt)}</p>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          <form className="chatInputRow" onSubmit={handleSend}>
            <textarea
              className="textInput"
              placeholder={canSend ? "Ask a question or request a summary..." : "Enable the model to start chatting."}
              value={messageDraft}
              onChange={(event) => setMessageDraft(event.target.value)}
              disabled={!canSend || sending}
            />
            <button
              className="button buttonSmall"
              type="submit"
              disabled={!canSend || sending || !messageDraft.trim()}
            >
              {sending ? "Queueing..." : "Send"}
            </button>
          </form>
        </div>

        <div className="chatSection chatSectionHighlight">
          <div className="chatSectionHeader">
            <div className="chatSectionHeaderMain">
              <p className="rowTitle">Conversations</p>
              <p className="muted tiny">{conversations.length} total</p>
            </div>
          </div>

          <div className="chatLists">
            <div className="chatQueueInline">
              <div className="chatSubHeader">
                <p className="muted tiny">Queued prompts</p>
                <div className="chatSectionMeta">
                  <span className="pill pill-neutral">{queueSummary}</span>
                  <span className="muted tiny">{queue?.total ?? 0} total</span>
                </div>
              </div>
              <div className="list queueList">
                {!queue ? (
                  <div className="skeleton" style={{ minHeight: 120 }} />
                ) : queue.items.length ? (
                  queue.items.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      className="row rowButton rowCompact"
                      onClick={() => setSelectedConversationId(item.conversationId)}
                    >
                      <div className={`dot dot-${queueTone(item.status)}`} />
                      <div className="rowMain">
                        <p className="rowTitle">{item.content}</p>
                        <p className="muted tiny">{item.status}</p>
                      </div>
                      <p className="rowDetail">{formatTimestamp(item.createdAt)}</p>
                    </button>
                  ))
                ) : (
                  <p className="muted tiny">No queued prompts yet.</p>
                )}
              </div>
            </div>

            <div className="chatConversationList">
              <div className="chatSubHeader">
                <p className="muted tiny">Conversation history</p>
                <p className="muted tiny">{conversations.length} total</p>
              </div>
              <div className="list">
                {!status ? (
                  <div className="skeleton" style={{ minHeight: 120 }} />
                ) : conversations.length ? (
                  conversations.map((item) => {
                    const active = item.id === selectedConversationId;
                    return (
                      <button
                        key={item.id}
                        type="button"
                        className={`row rowButton ${active ? "rowActive" : ""}`}
                        onClick={() => setSelectedConversationId(item.id)}
                      >
                        <div className="dot dot-neutral" />
                        <div className="rowMain">
                          <p className="rowTitle">{item.title}</p>
                          <p className="muted tiny">
                            {item.messageCount} messages
                            {item.lastMessage ? ` | ${item.lastMessage}` : ""}
                          </p>
                        </div>
                        <p className="rowDetail">{formatTimestamp(item.updatedAt)}</p>
                      </button>
                    );
                  })
                ) : (
                  <p className="muted tiny">No conversations saved yet.</p>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
