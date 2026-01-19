"use client";

import { LlmChatPanel } from "../components/LlmChatPanel";
import { PageHeader } from "../components/PageHeader";

export default function LlmAgentChatPage() {
  return (
    <>
      <PageHeader
        eyebrow="LLM-Agent Chat"
        title="Local Chat (Beta)"
        lede="Use the local agent to draft breakdowns, summaries, and next steps. Messages are queued and stored on this machine."
      />
      <LlmChatPanel />
    </>
  );
}
