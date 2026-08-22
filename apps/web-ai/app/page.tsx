"use client";

import { useEffect, useState } from "react";
import { gql } from "@fleetiq/gql-client";
import { sanitizeText } from "@fleetiq/sanitize";

export default function Page() {
  const [summary, setSummary] = useState("");

  useEffect(() => {
    gql<{ dashboard: { delayedDeliveries: number } }>(`query { dashboard { delayedDeliveries } }`)
      .then((d) => setSummary(`Delayed deliveries: ${d.dashboard.delayedDeliveries}`))
      .catch((e) => setSummary(e instanceof Error ? e.message : "Failed"));
  }, []);

  return (
    <main>
      <h2>{sanitizeText("AI remote")}</h2>
      <p>{sanitizeText(summary || "Loading ops context…")}</p>
    </main>
  );
}
