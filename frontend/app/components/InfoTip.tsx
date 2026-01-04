"use client";

import { useId, type KeyboardEvent } from "react";
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
  const alignClass = align === "center" ? "" : ` infoTipWrap-${align}`;
  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key === "Escape") {
      event.currentTarget.blur();
    }
  };
  return (
    <span className={`infoTipWrap${alignClass}`}>
      <button
        type="button"
        className="infoTip"
        aria-label={label}
        aria-describedby={id}
        onKeyDown={handleKeyDown}
      >
        <span aria-hidden>?</span>
      </button>
      <span id={id} role="tooltip" className="infoTipPanel">
        <Markdown content={content} className="markdown markdownTooltip" />
      </span>
    </span>
  );
}
