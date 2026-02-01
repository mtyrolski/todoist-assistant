"use client";

import { DashboardView } from "./components/DashboardView";
import { TokenGate } from "./components/TokenGate";

export default function Page() {
  return (
    <TokenGate>
      {({ setupActive, tokenReady, setupComplete }) => (
        <DashboardView setupActive={setupActive} tokenReady={tokenReady} setupComplete={setupComplete} />
      )}
    </TokenGate>
  );
}
