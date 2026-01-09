"use client";

import { MultiplicationSettings } from "../components/MultiplicationSettings";

export default function MultiplicationLabelsPage() {
  return (
    <>
      <header className="pageHeader">
        <div>
          <p className="eyebrow">Multiplication Labels</p>
          <h1>Task Multiplication Effects</h1>
          <p className="lede">
            Customize how labels like X3 or _X3 multiply tasks into flat copies or deep subtasks.
          </p>
        </div>
      </header>
      <MultiplicationSettings />
    </>
  );
}
