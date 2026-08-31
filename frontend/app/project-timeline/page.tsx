"use client";

import { ProjectTimelineView } from "../components/ProjectTimelineView";
import { TokenGate } from "../components/TokenGate";

export default function ProjectTimelinePage() {
  return <TokenGate>{() => <ProjectTimelineView />}</TokenGate>;
}
