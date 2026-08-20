"use client";

import { sanitizeText } from "@fleetiq/sanitize";

export default function Page() {
  return (
    <main>
      <h2>{sanitizeText("Analytics remote")}</h2>
      <p>{sanitizeText("KPI projections from the Analytics subgraph.")}</p>
    </main>
  );
}
