"use client";

import { useEffect, useState } from "react";
import { gql } from "@fleetiq/gql-client";
import { sanitizeText } from "@fleetiq/sanitize";

type Driver = { id: string; employeeCode: string; fullName: string; status: string };

export default function Page() {
  const [rows, setRows] = useState<Driver[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    gql<{ drivers: Driver[] }>(`query { drivers { id employeeCode fullName status } }`)
      .then((d) => setRows(d.drivers))
      .catch((e) => setError(sanitizeText(e instanceof Error ? e.message : "Failed")));
  }, []);

  return (
    <main>
      <h2>{sanitizeText("Drivers remote")}</h2>
      {error ? <p>{error}</p> : null}
      <ul>
        {rows.map((d) => (
          <li key={d.id}>
            {sanitizeText(d.employeeCode)} · {sanitizeText(d.fullName)}
          </li>
        ))}
      </ul>
    </main>
  );
}
