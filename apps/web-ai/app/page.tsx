"use client";

import { sanitizeText } from "@fleetiq/sanitize";

export default function Page() {
  return (
    <main>
      <h2>{sanitizeText("AI remote")}</h2>
      <p>{sanitizeText("Operations agent UI. Uses CORE / AI GraphQL via the gateway.")}</p>
    </main>
  );
}
