"use client";

import { useId, type KeyboardEvent } from "react";

function plainHelpText(content: string) {
  return content
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");
}

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
  const plainContent = plainHelpText(content);
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
        <span className="markdown markdownTooltip" style={{ whiteSpace: "pre-line" }}>
          {plainContent}
        </span>
      </span>
    </span>
  );
}
