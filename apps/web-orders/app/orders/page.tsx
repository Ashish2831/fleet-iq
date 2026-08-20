"use client";

import { sanitizeText } from "@fleetiq/sanitize";

export default function Page() {
  const title = sanitizeText("Orders remote");
  return (
    <main>
      <h2>{title}</h2>
      <p>{sanitizeText("Orders MFE on :3002. Shell rewrites /orders here when ORDERS_MFE_ORIGIN is set.")}</p>
    </main>
  );
}
