"use client";

import { LogInspector } from "../components/LogInspector";
import { PageHeader } from "../components/PageHeader";

export default function LiveLogsPage() {
  return (
    <>
      <PageHeader
        eyebrow="Operations"
        title="Live Log Inspector"
        lede="Read-only inspection for backend, frontend, Triton, observer, and automation runtime logs."
      />
      <LogInspector />
    </>
  );
}
