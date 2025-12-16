"use client";

export function LoadingBar({ active }: { active: boolean }) {
  if (!active) return null;
  return (
    <div className="loadingBar" aria-hidden>
      <div className="loadingBarInner" />
    </div>
  );
}

