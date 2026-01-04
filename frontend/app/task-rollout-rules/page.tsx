"use client";

import { TaskRolloutRules } from "../components/TaskRolloutRules";

export default function TaskRolloutRulesPage() {
  return (
    <>
      <header className="pageHeader">
        <div>
          <p className="eyebrow">Task Rollout Rules</p>
          <h1>LLM Breakdown Configuration</h1>
          <p className="lede">
            Tune how tasks are expanded into structured subtasks. Use variants to control depth, tone, and queueing.
          </p>
        </div>
      </header>
      <TaskRolloutRules />
    </>
  );
}
