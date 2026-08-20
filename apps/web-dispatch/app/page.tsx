"use client";

import { sanitizeText } from "@fleetiq/sanitize";

export default function Page() {
  return (
    <main>
      <h2>{sanitizeText("Dispatch remote")}</h2>
      <p>{sanitizeText("HITL proposals. Independent deploy; talks to Core via the gateway.")}</p>
    </main>
  );
}
