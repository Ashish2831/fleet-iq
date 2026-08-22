"use client";

import { useEffect, useState } from "react";
import { gql } from "@fleetiq/gql-client";
import { sanitizeText } from "@fleetiq/sanitize";

export default function Page() {
  const [kpis, setKpis] = useState("");

  useEffect(() => {
    gql<{
      dashboard: { activeVehicles: number; inTransitShipments: number; delayedDeliveries: number };
    }>(`query { dashboard { activeVehicles inTransitShipments delayedDeliveries } }`)
      .then((d) =>
        setKpis(
          `Active ${d.dashboard.activeVehicles} · In transit ${d.dashboard.inTransitShipments} · Delayed ${d.dashboard.delayedDeliveries}`,
        ),
      )
      .catch((e) => setKpis(e instanceof Error ? e.message : "Failed"));
  }, []);

  return (
    <main>
      <h2>{sanitizeText("Analytics remote")}</h2>
      <p>{sanitizeText(kpis || "Loading KPIs…")}</p>
    </main>
  );
}
