"use client";

import { useEffect, useState } from "react";
import { gql, sanitizeText } from "@/lib/api";

type Driver = {
  id: string;
  employeeCode: string;
  fullName: string;
  status: string;
  skills: string[];
  rating?: number | null;
};

export default function DriversPage() {
  const [rows, setRows] = useState<Driver[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    gql<{ drivers: Driver[] }>(`query { drivers { id employeeCode fullName status skills rating } }`)
      .then((d) => setRows(d.drivers))
      .catch((e) => setError(sanitizeText(e instanceof Error ? e.message : "Failed", 200)));
  }, []);
  return (
    <>
      <h2>Drivers</h2>
      {error ? <p className="err">{error}</p> : null}
      <table>
        <thead><tr><th>Code</th><th>Name</th><th>Status</th><th>Skills</th></tr></thead>
        <tbody>
          {rows.map((d) => (
            <tr key={d.id}>
              <td>{sanitizeText(d.employeeCode, 32)}</td>
              <td>{sanitizeText(d.fullName, 120)}</td>
              <td>{sanitizeText(d.status, 32)}</td>
              <td>{(d.skills || []).map((s) => sanitizeText(s, 32)).join(", ") || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
