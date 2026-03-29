"use client";

import { PageHeader } from "../components/PageHeader";
import { TaskIngestStudio } from "../components/TaskIngestStudio";
import { TokenGate } from "../components/TokenGate";

export default function TaskIngestPage() {
  return (
    <TokenGate>
      <PageHeader
        eyebrow="Task Ingest"
        title="Paste Raw Notes Into Task Trees"
        lede="Pick a project, paste rough content, and convert it into a structured Todoist task tree with nested subtasks."
      />
      <TaskIngestStudio />
    </TokenGate>
  );
}
