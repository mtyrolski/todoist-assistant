"use client";

type ProgressStep = {
  label: string;
  hint: string;
};

export type DashboardProgress = {
  active: boolean;
  stage: string | null;
  step: number;
  totalSteps: number;
  startedAt: string | null;
  updatedAt: string | null;
  detail: string | null;
  error: string | null;
};

const STEPS: ProgressStep[] = [
  {
    label: "Querying project data",
    hint: "Fetching projects and tasks"
  },
  {
    label: "Building project hierarchy",
    hint: "Resolving roots across active and archived projects"
  },
  {
    label: "Preparing dashboard data",
    hint: "Loading metadata and caches"
  }
];

const FALLBACK_TITLE = "Refreshing dashboard data";

function resolveStepIndex(progress: DashboardProgress): number {
  if (progress.step > 0) {
    return Math.min(progress.step - 1, STEPS.length - 1);
  }

  if (progress.stage) {
    const normalized = progress.stage.toLowerCase();
    const idx = STEPS.findIndex((step) => step.label.toLowerCase() === normalized);
    if (idx >= 0) return idx;
  }

  return 0;
}

export function ProgressSteps({ progress }: { progress: DashboardProgress | null }) {
  if (!progress?.active) return null;

  const stepIndex = resolveStepIndex(progress);
  const totalSteps = STEPS.length;
  const ratio = Math.min(1, (stepIndex + 1) / totalSteps);
  const activeStep = STEPS[stepIndex];
  const stageLabel = progress.stage ?? activeStep?.label ?? "Working";
  const detail = progress.detail ?? activeStep?.hint ?? "";

  return (
    <section className="progressCard" role="status" aria-live="polite">
      <div className="progressHeader">
        <div>
          <p className="progressTitle">{FALLBACK_TITLE}</p>
          <p className="progressStage">{stageLabel}</p>
          {detail ? <p className="progressDetail">{detail}</p> : null}
        </div>
        <p className="progressMeta">
          Step {Math.min(stepIndex + 1, totalSteps)} of {totalSteps}
        </p>
      </div>

      <div className="progressTrack" aria-hidden>
        <div className="progressFill" style={{ width: `${Math.round(ratio * 100)}%` }} />
        <div className="progressSweep" />
      </div>

      <div className="progressSteps" aria-hidden>
        {STEPS.map((step, idx) => {
          const state = idx < stepIndex ? "done" : idx === stepIndex ? "active" : "pending";
          return (
            <div key={step.label} className={`progressStep progressStep-${state}`}>
              <span className="progressDot" />
              <div>
                <p className="progressLabel">{step.label}</p>
                <p className="progressHint">{step.hint}</p>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
