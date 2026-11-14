"use client";

import { PageHeader } from "../components/PageHeader";
import { ProjectAdjustmentsBoard } from "../components/ProjectAdjustmentsBoard";

export default function ProjectAdjustmentsPage() {
  return (
    <>
      <PageHeader
        eyebrow="Operations"
        title="Project Adjustments"
        lede="Map archived projects into your current project hierarchy."
      />
      <ProjectAdjustmentsBoard showWhenEmpty />
    </>
  );
}
