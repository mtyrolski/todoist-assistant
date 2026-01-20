"use client";

import { MultiplicationSettings } from "../components/MultiplicationSettings";
import { PageHeader } from "../components/PageHeader";

export default function MultiplicationLabelsPage() {
  return (
    <>
      <PageHeader
        eyebrow="Multiplication Labels"
        title="Task Multiplication Effects"
        lede="Customize how labels like X3 or _X3 multiply tasks into flat copies or deep subtasks."
      />
      <MultiplicationSettings />
    </>
  );
}
