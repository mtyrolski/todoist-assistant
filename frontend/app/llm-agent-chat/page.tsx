"use client";

import { LlmChatPanel } from "../components/LlmChatPanel";
import { PageHeader } from "../components/PageHeader";

export default function LlmAgentChatPage() {
  return (
    <>
      <PageHeader
        eyebrow="LLM-Agent Chat"
        title="Chat (Beta)"
        lede="Use the chat surface to draft breakdowns, summaries, and next steps. Messages are queued and stored on this machine, with AI routed through Codex/langgraph-codex when enabled."
      />
      <LlmChatPanel />
    </>
  );
}
