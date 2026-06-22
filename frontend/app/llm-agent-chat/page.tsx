"use client";

import { LlmChatPanel } from "../components/LlmChatPanel";
import { PageHeader } from "../components/PageHeader";

export default function LlmAgentChatPage() {
  return (
    <>
      <PageHeader
        eyebrow="Codex"
        title="Personal Assistant"
        lede="Interactive chat for productivity questions, task proposals, status updates, and local cache or script-backed answers."
      />
      <LlmChatPanel />
    </>
  );
}
