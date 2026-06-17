"use client";

export function Markdown({ content, className }: { content: string; className?: string }) {
  return (
    <span className={className} style={{ whiteSpace: "pre-line" }}>
      {content}
    </span>
  );
}
