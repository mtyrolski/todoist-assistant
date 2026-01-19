"use client";

import type { ReactNode } from "react";

export function PageHeader({
  eyebrow,
  title,
  lede,
  children
}: {
  eyebrow: string;
  title: string;
  lede: string;
  children?: ReactNode;
}) {
  return (
    <header className="pageHeader">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p className="lede">{lede}</p>
        {children}
      </div>
    </header>
  );
}
