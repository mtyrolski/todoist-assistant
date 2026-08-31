"use client";

import { MultiplicationSettings } from "../components/MultiplicationSettings";
import { PageHeader } from "../components/PageHeader";

export default function MultiplicationLabelsPage() {
  return (
    <>
      <PageHeader
        eyebrow="Automation"
        title="Task Multiplication"
        lede="Use Xn labels to turn one task into a clear, repeatable set of work items."
      />
      <MultiplicationSettings />
    </>
  );
}
