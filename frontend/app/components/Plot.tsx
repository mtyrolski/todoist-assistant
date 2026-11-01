"use client";

import dynamic from "next/dynamic";
import type { PlotParams } from "react-plotly.js";

// Load Plotly's prebuilt distribution through the supported React factory.
// The npm alias satisfies the React peer dependency without source/build tools.
export const Plot = dynamic<PlotParams>(async () => {
  const [{ default: createPlotlyComponent }, { default: plotly }] = await Promise.all([
    import("react-plotly.js/factory"),
    import("plotly.js")
  ]);
  return createPlotlyComponent(plotly);
}, { ssr: false });
