"use client";

import { useEffect, useState } from "react";
import { gql } from "@/lib/api";

export default function VehiclesPage() {
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => {
    gql<{ vehicles: any[] }>(`query { vehicles { id plateNumber status make vehicleTypeName } }`).then((d) =>
      setRows(d.vehicles)
    );
  }, []);
  return (
    <>
      <h2>Vehicles</h2>
      <table>
        <thead><tr><th>Plate</th><th>Type</th><th>Status</th></tr></thead>
        <tbody>
          {rows.map((v) => (
            <tr key={v.id}>
              <td>{v.plateNumber}</td>
              <td>{v.vehicleTypeName}</td>
              <td>{v.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
