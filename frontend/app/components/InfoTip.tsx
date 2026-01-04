"use client";

import { useId } from "react";
import { Markdown } from "./Markdown";

export function InfoTip({
  label,
  content,
  align = "center"
}: {
  label: string;
  content: string;
  align?: "center" | "start" | "end";
}) {
  const id = useId();
  const alignClass = align === "center" ? "" : ` infoTip-${align}`;
  return (
    <button
      type="button"
      className={`infoTip${alignClass}`}
      aria-label={label}
      aria-describedby={id}
    >
      <span aria-hidden>?</span>
      <span id={id} role="tooltip" className="infoTipPanel">
        <Markdown content={content} className="markdown markdownTooltip" />
      </span>
    </button>
  );
}
