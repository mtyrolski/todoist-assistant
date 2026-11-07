"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import type { PlotParams } from "react-plotly.js";

// Load Plotly's prebuilt distribution through the supported React factory.
// The npm alias satisfies the React peer dependency without source/build tools.
const Plotly = dynamic<PlotParams>(async () => {
  const [{ default: createPlotlyComponent }, { default: plotly }] = await Promise.all([
    import("react-plotly.js/factory"),
    import("plotly.js")
  ]);
  return createPlotlyComponent(plotly);
}, { ssr: false });

export function Plot(props: PlotParams) {
  const [supported, setSupported] = useState<boolean | null>(null);

  useEffect(() => {
    // Plotly inserts a :focus-visible rule at load time, which throws on older WebViews.
    setSupported(typeof CSS !== "undefined" && CSS.supports("selector(:focus-visible)"));
  }, []);

  if (supported === null) return null;
  if (!supported) return <p>Charts require an updated Android System WebView or browser.</p>;
  return <Plotly {...props} />;
}
