"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

/** Keep Plotly charts near the viewport; once mounted they retain user interactions. */
export function DeferredPlot({ title, height, children }: { title: string; height: number; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    if (mounted) return;
    const node = ref.current;
    if (!node || typeof IntersectionObserver === "undefined") {
      setMounted(true);
      return;
    }
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) setMounted(true);
    }, { rootMargin: "600px 0px" });
    observer.observe(node);
    return () => observer.disconnect();
  }, [mounted]);

  return <div ref={ref}>{mounted ? children : <section className="card" aria-label={title} aria-busy="true" style={{ minHeight: height + 80 }}><header className="cardHeader"><h2>{title}</h2></header></section>}</div>;
}
