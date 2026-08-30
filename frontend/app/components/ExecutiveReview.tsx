"use client";

import { useEffect, useState } from "react";
import { Markdown } from "./Markdown";

type ReviewResponse = {
  enabled: boolean;
  summary: string | null;
  detail?: string;
  loading?: boolean;
};

export function ExecutiveReview() {
  const [response, setResponse] = useState<ReviewResponse | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const restore = async () => {
      try {
        const result = await fetch("/api/dashboard/executive_review");
        const body = (await result.json()) as ReviewResponse;
        if (!active) return;
        setResponse(body);
        setLoading(Boolean(body.loading));
        if (body.loading) timer = setTimeout(restore, 1500);
      } catch {
        if (active) setLoading(false);
      }
    };
    void restore();
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
    };
  }, []);

  const generate = async (refresh = false) => {
    setLoading(true);
    try {
      const result = await fetch(`/api/dashboard/executive_review${refresh ? "?refresh=true" : ""}`, { method: "POST" });
      const body = (await result.json()) as ReviewResponse;
      setResponse(
        result.ok
          ? body
          : {
              enabled: false,
              summary: null,
              detail: body.detail ?? `The review request failed (${result.status}).`
            }
      );
    } catch {
      setResponse({
        enabled: false,
        summary: null,
        detail: "The dashboard API did not return a readable review response. Check the API status and try again."
      });
    } finally {
      setLoading(false);
    }
  };

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
