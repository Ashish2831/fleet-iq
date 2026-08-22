"use client";

import { useVehiclesQuery } from "@/lib/queries";
import { sanitizeText } from "@/lib/sanitize";

export default function VehiclesPage() {
  const { data: rows = [], error } = useVehiclesQuery();
  return (
    <>
      <h2>Vehicles</h2>
      {error ? <p className="err">{sanitizeText(error.message, 200)}</p> : null}
      <table>
        <thead>
          <tr>
            <th>Plate</th>
            <th>Type</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((v) => (
            <tr key={v.id}>
              <td>{sanitizeText(v.plateNumber, 32)}</td>
              <td>{sanitizeText(v.vehicleTypeName, 64)}</td>
              <td>{sanitizeText(v.status, 32)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
