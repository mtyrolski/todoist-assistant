export type TimelineStatus = "completed" | "ongoing" | "unresolved" | "inactive";

export type ProjectTimelineChild = {
  id: string;
  name: string;
  status: TimelineStatus;
  startDate: string;
  endDate: string | null;
  visualStart: string;
  visualEnd: string;
  completionDate: string | null;
  archiveDate: string | null;
  archived: boolean;
  durationDays: number;
  completions: number;
  openTasks: number;
};

export type ProjectTimelineParent = {
  id: string;
  name: string;
  children: ProjectTimelineChild[];
};

export type ProjectTimelineData = {
  range: { start: string; end: string } | null;
  parents: ProjectTimelineParent[];
  refreshedAt?: string;
  error?: string;
};
