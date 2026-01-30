"use client";

import { DashboardView } from "./components/DashboardView";
import { TokenGate } from "./components/TokenGate";

export default function Page() {
  return (
    <TokenGate>
      <DashboardView />
    </TokenGate>
  );
}
