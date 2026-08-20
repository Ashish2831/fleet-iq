"use client";

import { useEffect, useState } from "react";
import { gql, sanitizeText } from "@/lib/api";

type Vehicle = {
  id: string;
  plateNumber: string;
  status: string;
  make?: string;
  vehicleTypeName?: string;
};

export default function VehiclesPage() {
  const [rows, setRows] = useState<Vehicle[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    gql<{ vehicles: Vehicle[] }>(`query { vehicles { id plateNumber status make vehicleTypeName } }`)
      .then((d) => setRows(d.vehicles))
      .catch((e) => setError(sanitizeText(e instanceof Error ? e.message : "Failed", 200)));
  }, []);
  return (
    <>
      <h2>Vehicles</h2>
      {error ? <p className="err">{error}</p> : null}
      <table>
        <thead><tr><th>Plate</th><th>Type</th><th>Status</th></tr></thead>
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
