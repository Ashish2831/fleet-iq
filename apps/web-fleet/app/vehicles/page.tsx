"use client";

import { useEffect, useState } from "react";
import { gql } from "@fleetiq/gql-client";
import { sanitizeText } from "@fleetiq/sanitize";

type Vehicle = { id: string; plateNumber: string; status: string; vehicleTypeName?: string };

export default function Page() {
  const [rows, setRows] = useState<Vehicle[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    gql<{ vehicles: Vehicle[] }>(`query { vehicles { id plateNumber status vehicleTypeName } }`)
      .then((d) => setRows(d.vehicles))
      .catch((e) => setError(sanitizeText(e instanceof Error ? e.message : "Failed")));
  }, []);

  return (
    <main>
      <h2>{sanitizeText("Vehicles remote")}</h2>
      {error ? <p>{error}</p> : null}
      <ul>
        {rows.map((v) => (
          <li key={v.id}>
            {sanitizeText(v.plateNumber)} · {sanitizeText(v.status)}
          </li>
        ))}
      </ul>
    </main>
  );
}
