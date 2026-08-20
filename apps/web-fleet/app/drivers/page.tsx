"use client";

import { sanitizeText } from "@fleetiq/sanitize";

export default function Page() {
  return (
    <main>
      <h2>{sanitizeText("Drivers remote")}</h2>
      <p>
        {sanitizeText("Fleet MFE. Auth token is the Core JWT in localStorage (fq_access).")}
      </p>
    </main>
  );
}
