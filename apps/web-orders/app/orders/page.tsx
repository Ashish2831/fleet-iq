"use client";

import { useEffect, useState } from "react";
import { gql } from "@fleetiq/gql-client";
import { sanitizeText } from "@fleetiq/sanitize";

type Order = { id: string; orderNumber: string; status: string };

export default function Page() {
  const [rows, setRows] = useState<Order[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    gql<{ orders: Order[] }>(`query { orders(first: 50) { id orderNumber status } }`)
      .then((d) => setRows(d.orders))
      .catch((e) => setError(sanitizeText(e instanceof Error ? e.message : "Failed")));
  }, []);

  return (
    <main>
      <h2>{sanitizeText("Orders remote")}</h2>
      {error ? <p>{error}</p> : null}
      <ul>
        {rows.map((o) => (
          <li key={o.id}>
            {sanitizeText(o.orderNumber)} · {sanitizeText(o.status)}
          </li>
        ))}
      </ul>
    </main>
  );
}
