"use client";

import { PageHeader } from "../components/PageHeader";
import { StatusUpdateStudio } from "../components/StatusUpdateStudio";
import { TokenGate } from "../components/TokenGate";

export default function StatusUpdatesPage() {
  return (
    <TokenGate>
      <PageHeader
        eyebrow="Automation Studio"
        title="Status Update Studio"
        lede="Select projects and a date range, then generate a sync-ready update from completed tasks and their comments."
      />
      <StatusUpdateStudio />
    </TokenGate>
  );
}
