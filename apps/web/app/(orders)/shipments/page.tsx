"use client";

import { useEffect, useState } from "react";
import { gql, sanitizeText } from "@/lib/api";

type Shipment = { id: string; shipmentNumber: string; status: string; promisedAt?: string | null };

export default function ShipmentsPage() {
  const [rows, setRows] = useState<Shipment[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    gql<{ shipments: Shipment[] }>(`query { shipments { id shipmentNumber status promisedAt } }`)
      .then((d) => setRows(d.shipments))
      .catch((e) => setError(sanitizeText(e instanceof Error ? e.message : "Failed", 200)));
  }, []);
  return (
    <>
      <h2>Shipments</h2>
      {error ? <p className="err">{error}</p> : null}
      <table>
        <thead><tr><th>Number</th><th>Status</th><th>Promised</th></tr></thead>
        <tbody>
          {rows.map((s) => (
            <tr key={s.id}>
              <td>{sanitizeText(s.shipmentNumber, 64)}</td>
              <td>{sanitizeText(s.status, 32)}</td>
              <td>{s.promisedAt ? new Date(s.promisedAt).toLocaleString() : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
