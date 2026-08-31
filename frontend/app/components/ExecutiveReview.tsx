"use client";

import { useEffect, useState } from "react";
import { Markdown } from "./Markdown";

type ReviewStatus = "idle" | "running" | "completed" | "failed";

type ReviewResponse = {
  enabled: boolean;
  runId: string | null;
  status: ReviewStatus;
  summary: string | null;
  detail?: string | null;
};

async function requestReview(method: "GET" | "POST" = "GET", refresh = false): Promise<ReviewResponse> {
  const result = await fetch(`/api/dashboard/executive_review${refresh ? "?refresh=true" : ""}`, { method });
  const body = (await result.json()) as ReviewResponse;
  if (!result.ok) throw new Error(body.detail ?? `The review request failed (${result.status}).`);
  return body;
}

export function ExecutiveReview() {
  const [response, setResponse] = useState<ReviewResponse | null>(null);
  const status = response?.status;

  useEffect(() => {
    if (status && status !== "running") return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const body = await requestReview();
        if (cancelled) return;
        setResponse(body);
        if (body.status === "running") timer = setTimeout(poll, 1500);
      } catch (error) {
        if (cancelled) return;
        setResponse((current) => ({
          enabled: current?.enabled ?? false,
          runId: current?.runId ?? null,
          status: "failed",
          summary: null,
          detail: error instanceof Error ? error.message : "Unable to restore the weekly brief."
        }));
      }
    };
    timer = setTimeout(poll, status === "running" ? 1500 : 0);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [status]);

  const generate = async (refresh = false) => {
    if (status === "running") return;
    setResponse({
      enabled: response?.enabled ?? true,
      runId: response?.runId ?? null,
      status: "running",
      summary: response?.summary ?? null
    });
    try {
      setResponse(await requestReview("POST", refresh));
    } catch (error) {
      setResponse({
        enabled: false,
        runId: null,
        status: "failed",
        summary: null,
        detail:
          error instanceof Error
            ? error.message
            : "The dashboard API did not return a readable review response. Check the API status and try again."
      });
    }
  };

  const loading = status === "running";

  return (
    <section id="executive-review" className="card executiveReview jumpTarget">
      <header className="executiveReviewHeader">
        <div>
          <p className="executiveReviewEyebrow">Weekly brief</p>
          <h2>What changed, and what deserves focus now?</h2>
          <p className="executiveReviewIntro">
            A read-only Codex review of your cached activity, project load, completion rhythm, and recent momentum.
          </p>
        </div>
        <button
          className="button executiveReviewAction"
          type="button"
          onClick={() => generate(Boolean(response?.summary))}
          disabled={loading}
        >
          {loading ? "Analyzing…" : response?.summary ? "Refresh brief" : "Analyze last week"}
        </button>
      </header>
      {loading ? (
        <div className="executiveReviewLoading" role="status" aria-live="polite">
          <span />
          Comparing recent work with the preceding weeks…
        </div>
      ) : response?.summary ? (
        <div className="executiveReviewResult" aria-live="polite">
          <Markdown className="executiveReviewBody" content={response.summary} />
        </div>
      ) : response?.detail ? (
        <div className="executiveReviewError" role="alert">
          <strong>Review unavailable</strong>
          <span>{response.detail}</span>
        </div>
      ) : (
        <div className="executiveReviewSignals" aria-label="Review contents">
          <span>7-day comparison</span>
          <span>Project pressure</span>
          <span>Completion hours</span>
          <span>One next-focus flow</span>
        </div>
      )}
    </section>
  );
}
