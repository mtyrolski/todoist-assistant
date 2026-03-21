"use client";

import { ExperimentalHabitTrackerView } from "../../components/ExperimentalHabitTrackerView";
import { TokenGate } from "../../components/TokenGate";

export default function ExperimentalHabitsPage() {
  return (
    <TokenGate>
      <ExperimentalHabitTrackerView />
    </TokenGate>
  );
}
