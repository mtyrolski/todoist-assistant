"use client";

import { TaskTemplateManager } from "../components/TaskTemplateManager";

export default function TaskTemplatesPage() {
  return (
    <>
      <header className="pageHeader">
        <div>
          <p className="eyebrow">Task Templates</p>
          <h1>Reusable Task Blueprints</h1>
          <p className="lede">
            Create, edit, and organize templates that expand into full task trees when you apply a template label.
          </p>
        </div>
      </header>
      <TaskTemplateManager />
    </>
  );
}
