"use client";

import { PageHeader } from "../components/PageHeader";
import { TaskRolloutRules } from "../components/TaskRolloutRules";

export default function TaskRolloutRulesPage() {
  return (
    <>
      <PageHeader
        eyebrow="Task Rollout Rules"
        title="LLM Breakdown Configuration"
        lede="Tune how tasks are expanded into structured subtasks. Use variants to control depth, tone, and queueing."
      />
      <TaskRolloutRules />
    </>
  );
}
