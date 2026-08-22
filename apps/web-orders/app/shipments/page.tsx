"use client";

import { useEffect, useState } from "react";
import { gql } from "@fleetiq/gql-client";
import { sanitizeText } from "@fleetiq/sanitize";

type Shipment = { id: string; shipmentNumber: string; status: string };

export default function Page() {
  const [rows, setRows] = useState<Shipment[]>([]);

  useEffect(() => {
    gql<{ shipments: Shipment[] }>(`query { shipments { id shipmentNumber status } }`).then((d) =>
      setRows(d.shipments),
    );
  }, []);

  return (
    <main>
      <h2>{sanitizeText("Shipments remote")}</h2>
      <ul>
        {rows.map((s) => (
          <li key={s.id}>
            {sanitizeText(s.shipmentNumber)} · {sanitizeText(s.status)}
          </li>
        ))}
      </ul>
    </main>
  );
}
