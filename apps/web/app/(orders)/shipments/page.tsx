"use client";

import { useShipmentsQuery } from "@/lib/queries";
import { sanitizeText } from "@/lib/sanitize";

export default function ShipmentsPage() {
  const { data: rows = [], error } = useShipmentsQuery();
  return (
    <>
      <h2>Shipments</h2>
      {error ? <p className="err">{sanitizeText(error.message, 200)}</p> : null}
      <table>
        <thead>
          <tr>
            <th>Number</th>
            <th>Status</th>
            <th>Promised</th>
          </tr>
        </thead>
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
