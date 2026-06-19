"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Markdown } from "./Markdown";

type ChatConversationSummary = {
  id: string;
  title: string;
  createdAt?: string | null;
  updatedAt?: string | null;
  messageCount: number;
  lastMessage?: string | null;
};

type ChatMessage = {
  role: "system" | "user" | "assistant" | "tool" | string;
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
  backend: {
    selected: string;
    label: string;
    codex?: {
      model?: string | null;
    };
  };
  usage?: {
    totals?: {
      inferenceCount?: number;
      inputTokens?: number;
      outputTokens?: number;
      totalTokens?: number;
    };
    lastRequest?: {
      operation?: string | null;
      totalTokens?: number;
    } | null;
  };
  assistant?: {
    tools?: string[];
    scripts?: Array<{ name: string; path: string; command: string }>;
    telemetry?: {
      enabled: boolean;
      endpointConfigured: boolean;
    };
  };
  conversations: ChatConversationSummary[];
};

type SendResponse = {
  conversationId?: string;
  conversation?: ChatConversation;
  detail?: string;
};

type OperationEvent = {
  title: string;
  status: "running" | "complete" | "failed";
  detailLabel: string;
  detail: string;
};

const POLL_MS = 7000;
const PYTHON_CALL_PREFIX = "Calling python_repl with code:";
const PYTHON_OUTPUT_PREFIX = "python_repl output:";

function formatTimestamp(value?: string | null): string {
  if (!value) return "--";
  return value.replace("T", " ");
}

function formatCount(value?: number | null): string {
  return typeof value === "number" ? value.toLocaleString() : "0";
}

function runtimeLabel(status: ChatStatus | null): string {
  if (!status) return "Codex status unknown";
  if (status.enabled) return "Codex ready";
  if (status.loading) return "Codex loading";
  return "Codex cold";
}

function messageLabel(role: string): string {
  if (role === "assistant") return "Codex";
  if (role === "user") return "You";
  return role;
}

function extractPythonCode(content: string): string {
  const fenced = content.match(/```python\n([\s\S]*?)\n```/);
  if (fenced?.[1]) return fenced[1].trim();
  return content.replace(PYTHON_CALL_PREFIX, "").trim();
}

function quotedArg(code: string, fnName: string): string | null {
  const pattern = new RegExp(`${fnName}\\(\\s*['"]([^'"]+)['"]`);
  return code.match(pattern)?.[1] ?? null;
}

function operationTitleFromCode(code: string): string {
  const scriptName = quotedArg(code, "run_script");
  if (scriptName) return `Running script: ${scriptName}`;
  const cacheName = quotedArg(code, "load_cache");
  if (cacheName) return `Reading cache: ${cacheName}`;
  if (code.includes("cache_summary(")) return "Checking local cache";
  if (code.includes("script_catalog(")) return "Checking available scripts";
  if (code.includes("llm_usage(")) return "Checking token usage";
  if (code.includes("telemetry_status(")) return "Checking telemetry";
  if (code.includes("projects(")) return "Reading Todoist projects";
  if (code.includes("create_tasks(")) return "Creating Todoist tasks";
  return "Running Python tool";
}

function operationFromMessage(message: ChatMessage): OperationEvent | null {
  const content = message.content ?? "";
  if (content.startsWith(PYTHON_CALL_PREFIX)) {
    const code = extractPythonCode(content);
    return {
      title: operationTitleFromCode(code),
      status: "running",
      detailLabel: "Code",
      detail: code
    };
  }
  if (content.startsWith(PYTHON_OUTPUT_PREFIX)) {
    const output = content.replace(PYTHON_OUTPUT_PREFIX, "").trim();
    const failed = output.startsWith("ERROR:");
    return {
      title: failed ? "Operation failed" : "Operation result",
      status: failed ? "failed" : "complete",
      detailLabel: "Output",
      detail: output || "No output"
    };
  }
  if (message.role === "tool") {
    return {
      title: "Tool event",
      status: content.startsWith("ERROR:") ? "failed" : "complete",
      detailLabel: "Output",
      detail: content
    };
  }
  return null;
}

function OperationEventCard({ event, createdAt }: { event: OperationEvent; createdAt?: string | null }) {
  return (
    <article className={`assistantOperation assistantOperation-${event.status}`}>
      <div className="assistantOperationLine">
        <span className="assistantOperationDot" aria-hidden />
        <div className="assistantOperationMain">
          <div className="assistantOperationHeader">
            <span>{event.title}</span>
            <span>{formatTimestamp(createdAt)}</span>
          </div>
          <details className="assistantOperationDetails">
            <summary>{event.detailLabel}</summary>
            <pre>{event.detail}</pre>
          </details>
        </div>
      </div>
    </article>
  );
}

export function LlmChatPanel() {
  const [status, setStatus] = useState<ChatStatus | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [loadingStatus, setLoadingStatus] = useState(false);

  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  const [conversation, setConversation] = useState<ChatConversation | null>(null);
  const [loadingConversation, setLoadingConversation] = useState(false);

  const [messageDraft, setMessageDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const didAutoSelect = useRef(false);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const conversations = status?.conversations ?? [];
  const selectedSummary = useMemo(() => {
    if (!selectedConversationId) return null;
    return conversations.find((item) => item.id === selectedConversationId) ?? null;
  }, [conversations, selectedConversationId]);

  const refreshStatus = useCallback(async (silent = false) => {
    try {
      if (!silent) setLoadingStatus(true);
      setStatusError(null);
      const res = await fetch("/api/dashboard/llm_chat");
      const payload = (await res.json()) as ChatStatus & { detail?: string };
      if (!res.ok) {
        throw new Error(payload.detail ?? "Failed to load chat status");
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
      const payload = (await res.json()) as ChatConversation & { detail?: string };
      if (!res.ok) {
        throw new Error(payload.detail ?? "Failed to load conversation");
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
    if (didAutoSelect.current || !conversations.length) return;
    setSelectedConversationId(conversations[0].id);
    didAutoSelect.current = true;
  }, [conversations]);

  useEffect(() => {
    if (!selectedConversationId) {
      setConversation(null);
      return;
    }
    if (status && !conversations.some((item) => item.id === selectedConversationId)) {
      setSelectedConversationId(null);
      return;
    }
    if (conversation?.id === selectedConversationId && conversation?.updatedAt === selectedSummary?.updatedAt) return;
    loadConversation(selectedConversationId);
  }, [
    conversations,
    conversation?.id,
    conversation?.updatedAt,
    loadConversation,
    selectedConversationId,
    selectedSummary?.updatedAt,
    status
  ]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ block: "end" });
  }, [conversation?.messages.length, sending]);

  const handleEnable = async () => {
    try {
      setActionError(null);
      const res = await fetch("/api/llm_chat/enable", { method: "POST" });
      const payload = (await res.json()) as { detail?: string };
      if (!res.ok) {
        throw new Error(payload.detail ?? "Failed to warm up Codex");
      }
      await refreshStatus();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to warm up Codex");
    }
  };

  const handleSend = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = messageDraft.trim();
    if (!trimmed || sending) return;

    const optimisticMessage: ChatMessage = {
      role: "user",
      content: trimmed,
      createdAt: new Date().toISOString().slice(0, 19)
    };
    if (!conversation) {
      setConversation({
        id: selectedConversationId ?? "pending",
        title: trimmed.slice(0, 80),
        messages: [optimisticMessage]
      });
    } else {
      setConversation({ ...conversation, messages: [...conversation.messages, optimisticMessage] });
    }

    try {
      setActionError(null);
      setSending(true);
      const body = selectedConversationId ? { message: trimmed, conversationId: selectedConversationId } : { message: trimmed };
      const res = await fetch("/api/llm_chat/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });
      const payload = (await res.json()) as SendResponse;
      if (!res.ok) {
        throw new Error(payload.detail ?? "Failed to run assistant turn");
      }
      setMessageDraft("");
      if (payload.conversationId) {
        setSelectedConversationId(payload.conversationId);
      }
      if (payload.conversation) {
        setConversation(payload.conversation);
      }
      await refreshStatus(true);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to run assistant turn");
    } finally {
      setSending(false);
    }
  };

  const model = status?.backend.codex?.model ?? status?.backend.label ?? "Codex";
  const canSend = !sending;

  return (
    <section className="assistantWorkspace">
      <aside className="assistantRail" aria-label="Conversations">
        <div className="assistantRailHeader">
          <div>
            <p className="muted tiny">Chats</p>
            <p className="rowTitle">{conversations.length} saved</p>
          </div>
          <button
            className="button buttonSmall"
            type="button"
            onClick={() => {
              setSelectedConversationId(null);
              setConversation(null);
              setMessageDraft("");
            }}
          >
            New
          </button>
        </div>

        <div className="assistantConversationList">
          {!status ? (
            <div className="skeleton" style={{ minHeight: 120 }} />
          ) : conversations.length ? (
            conversations.map((item) => {
              const active = item.id === selectedConversationId;
              return (
                <button
                  key={item.id}
                  type="button"
                  className={`assistantConversationButton${active ? " assistantConversationButtonActive" : ""}`}
                  onClick={() => setSelectedConversationId(item.id)}
                >
                  <span className="assistantConversationTitle">{item.title}</span>
                  <span className="assistantConversationMeta">
                    {item.messageCount} messages | {formatTimestamp(item.updatedAt)}
                  </span>
                  {item.lastMessage ? <span className="assistantConversationPreview">{item.lastMessage}</span> : null}
                </button>
              );
            })
          ) : (
            <p className="muted tiny">No saved chats.</p>
          )}
        </div>
      </aside>

      <div className="assistantMain">
        <header className="assistantTopbar">
          <div>
            <p className="muted tiny">Personal Assistant</p>
            <h1>{conversation?.title ?? selectedSummary?.title ?? "New chat"}</h1>
          </div>
          <div className="assistantActions">
            <button className="button buttonSmall" type="button" onClick={handleEnable} disabled={status?.enabled || status?.loading}>
              {status?.enabled ? "Ready" : status?.loading ? "Loading" : "Warm"}
            </button>
            <button className="button buttonSmall" type="button" onClick={() => refreshStatus()} disabled={loadingStatus}>
              {loadingStatus ? "Refreshing" : "Refresh"}
            </button>
          </div>
        </header>

        <div className="assistantRuntime">
          <span className={`pill ${status?.enabled ? "pill-good" : status?.loading ? "pill-neutral" : "pill-warn"}`}>
            {runtimeLabel(status)}
          </span>
          <span className="pill pill-neutral">Model {model}</span>
          <span className="pill pill-neutral">{formatCount(status?.usage?.totals?.totalTokens)} tokens</span>
          <span className="pill pill-neutral">
            Input {formatCount(status?.usage?.totals?.inputTokens)} / Output {formatCount(status?.usage?.totals?.outputTokens)}
          </span>
          <span className="pill pill-neutral">Inferences {formatCount(status?.usage?.totals?.inferenceCount)}</span>
          <span className="pill pill-neutral">
            Tools {status?.assistant?.tools?.length ?? 0} / Scripts {status?.assistant?.scripts?.length ?? 0}
          </span>
          <span className="pill pill-neutral">
            Telemetry {status?.assistant?.telemetry?.enabled ? "on" : "off"}
            {status?.assistant?.telemetry?.endpointConfigured ? " / endpoint set" : " / endpoint unset"}
          </span>
          {status?.usage?.lastRequest ? (
            <span className="pill pill-neutral">
              Last {status.usage.lastRequest.operation ?? "request"} {formatCount(status.usage.lastRequest.totalTokens)} tokens
            </span>
          ) : null}
        </div>

        {statusError ? <p className="muted tiny">Status error: {statusError}</p> : null}
        {actionError ? <p className="muted tiny">Error: {actionError}</p> : null}

        <div className="assistantMessages" aria-live="polite">
          {loadingConversation ? (
            <div className="skeleton" style={{ minHeight: 180 }} />
          ) : conversation?.messages?.length ? (
            conversation.messages.map((msg, idx) => {
              const content = msg.content ?? "";
              const operation = operationFromMessage(msg);
              if (operation) {
                return <OperationEventCard key={`${msg.role}-${idx}`} event={operation} createdAt={msg.createdAt} />;
              }
              return (
                <article key={`${msg.role}-${idx}`} className={`assistantMessage assistantMessage-${msg.role}`}>
                  <div className="assistantMessageMeta">
                    <span>{messageLabel(msg.role)}</span>
                    <span>{formatTimestamp(msg.createdAt)}</span>
                  </div>
                  <Markdown content={content} className="markdown markdownChat" />
                </article>
              );
            })
          ) : (
            <div className="assistantEmptyState">
              <p>Ask Codex about productivity stats, status updates, or pasted files.</p>
            </div>
          )}
          {sending ? (
            <article className="assistantMessage assistantMessage-assistant assistantMessagePending">
              <div className="assistantMessageMeta">
                <span>Codex</span>
                <span>running</span>
              </div>
              <div className="assistantTyping">
                <span />
                <span />
                <span />
              </div>
            </article>
          ) : null}
          <div ref={messagesEndRef} />
        </div>

        <form className="assistantComposer" onSubmit={handleSend}>
          <textarea
            className="textInput"
            placeholder="Paste notes, ask for status, propose tasks, or query local productivity stats."
            value={messageDraft}
            onChange={(event) => setMessageDraft(event.target.value)}
            disabled={!canSend}
          />
          <button className="button" type="submit" disabled={!canSend || !messageDraft.trim()}>
            {sending ? "Running" : "Send"}
          </button>
        </form>
      </div>
    </section>
  );
}
