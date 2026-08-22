"use client";

import { useEffect, useState } from "react";
import { gql } from "@fleetiq/gql-client";
import { sanitizeText } from "@fleetiq/sanitize";

export default function Page() {
  const [n, setN] = useState<number | null>(null);

  useEffect(() => {
    gql<{ dashboard: { activeVehicles: number } }>(`query { dashboard { activeVehicles } }`)
      .then((d) => setN(d.dashboard.activeVehicles))
      .catch(() => setN(null));
  }, []);

  return (
    <main>
      <h2>{sanitizeText("Fleet remote")}</h2>
      <p>{sanitizeText("Live map origin :3001. Active vehicles from GraphQL:")} {n ?? "—"}</p>
    </main>
  );
}
