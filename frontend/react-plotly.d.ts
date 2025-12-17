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
