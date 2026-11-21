"use client";

import { DashboardView } from "./components/DashboardView";
import { TokenGate } from "./components/TokenGate";

export default function Page() {
  return (
    <TokenGate>
      {({ setupActive, tokenReady }) => (
        <DashboardView setupActive={setupActive} tokenReady={tokenReady} />
      )}
    </TokenGate>
  );
}
