"use client";

import { sanitizeText } from "@fleetiq/sanitize";

export default function Page() {
  return (
    <main>
      <h2>{sanitizeText("Vehicles remote")}</h2>
      <p>
        {sanitizeText("Fleet MFE — vehicle master list. Data still comes from the GraphQL gateway.")}
      </p>
    </main>
  );
}
