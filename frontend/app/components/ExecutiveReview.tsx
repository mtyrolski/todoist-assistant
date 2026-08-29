"use client";

import { useState } from "react";
import { Markdown } from "./Markdown";

type ReviewResponse = {
  enabled: boolean;
  summary: string | null;
  detail?: string;
};

export function ExecutiveReview() {
  const [response, setResponse] = useState<ReviewResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const generate = async (refresh = false) => {
    setLoading(true);
    try {
      const result = await fetch(`/api/dashboard/executive_review${refresh ? "?refresh=true" : ""}`, { method: "POST" });
      setResponse((await result.json()) as ReviewResponse);
    } catch {
      setResponse({ enabled: false, summary: null, detail: "The executive review could not be generated." });
    } finally {
      setLoading(false);
    }
  };

  return (
    <section id="executive-review" className="card executiveReview jumpTarget">
      <header className="cardHeader">
        <div className="cardTitleRow">
          <h2>Executive review</h2>
          <span className="pill pill-neutral">Local activity analysis</span>
        </div>
        <button className="button buttonSmall" type="button" onClick={() => generate(Boolean(response?.summary))} disabled={loading}>
          {loading ? "Reviewing..." : response?.summary ? "Refresh review" : "Generate review"}
        </button>
      </header>
      {response?.summary ? (
        <Markdown className="executiveReviewBody" content={response.summary} />
      ) : (
        <p className="muted">{response?.detail ?? "Compare the latest week with prior activity, project load, completion rhythm, and the next focus flow."}</p>
      )}
    </section>
  );
}
