declare module "react-plotly.js" {
  import * as React from "react";

  export type PlotParams = {
    data: unknown[];
    layout?: Record<string, unknown>;
    frames?: unknown[];
    config?: Record<string, unknown>;
    useResizeHandler?: boolean;
    style?: React.CSSProperties;
    className?: string;
  };

  const Plot: React.ComponentType<PlotParams>;
  export default Plot;
}

declare module "react-plotly.js/factory" {
  import type { ComponentType } from "react";
  import type { PlotParams } from "react-plotly.js";
  export default function createPlotlyComponent(plotly: unknown): ComponentType<PlotParams>;
}

declare module "plotly.js" {
  const plotly: unknown;
  export default plotly;
}
