"use client";

import { sanitizeText } from "@fleetiq/sanitize";

export default function Page() {
  return (
    <main>
      <h2>{sanitizeText("Fleet remote")}</h2>
      <p>
        {sanitizeText(
          "Live map ships from this origin (:3001). Shell rewrites /live-map here when FLEET_MFE_ORIGIN is set.",
        )}
      </p>
    </main>
  );
}
