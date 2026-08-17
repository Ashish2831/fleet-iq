"use client";

import { useEffect, useState } from "react";
import { gql } from "@/lib/api";

export default function ShipmentsPage() {
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => {
    gql<{ shipments: any[] }>(`query { shipments { id shipmentNumber status promisedAt } }`).then((d) =>
      setRows(d.shipments)
    );
  }, []);
  return (
    <>
      <h2>Shipments</h2>
      <table>
        <thead><tr><th>Number</th><th>Status</th><th>Promised</th></tr></thead>
        <tbody>
          {rows.map((s) => (
            <tr key={s.id}>
              <td>{s.shipmentNumber}</td>
              <td>{s.status}</td>
              <td>{s.promisedAt ? new Date(s.promisedAt).toLocaleString() : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
