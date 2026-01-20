"use client";

import { PageHeader } from "../components/PageHeader";
import { TaskTemplateManager } from "../components/TaskTemplateManager";

export default function TaskTemplatesPage() {
  return (
    <>
      <PageHeader
        eyebrow="Task Templates"
        title="Reusable Task Blueprints"
        lede="Create, edit, and organize templates that expand into full task trees when you apply a template label."
      />
      <TaskTemplateManager />
    </>
  );
}
