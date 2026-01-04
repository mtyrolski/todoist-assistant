"use client";

import { LlmChatPanel } from "../components/LlmChatPanel";

export default function LlmAgentChatPage() {
  return (
    <>
      <header className="pageHeader">
        <div>
          <p className="eyebrow">LLM-Agent Chat</p>
          <h1>Local Chat (Beta)</h1>
          <p className="lede">
            Use the local agent to draft breakdowns, summaries, and next steps. Messages are queued and stored on this
            machine.
          </p>
        </div>
      </header>
      <LlmChatPanel />
    </>
  );
}
