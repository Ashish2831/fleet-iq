"use client";

import { useEffect, useState } from "react";
import { gql } from "@/lib/api";

export default function DriversPage() {
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => {
    gql<{ drivers: any[] }>(`query { drivers { id employeeCode fullName status skills rating } }`).then((d) =>
      setRows(d.drivers)
    );
  }, []);
  return (
    <>
      <h2>Drivers</h2>
      <table>
        <thead><tr><th>Code</th><th>Name</th><th>Status</th><th>Skills</th></tr></thead>
        <tbody>
          {rows.map((d) => (
            <tr key={d.id}>
              <td>{d.employeeCode}</td>
              <td>{d.fullName}</td>
              <td>{d.status}</td>
              <td>{(d.skills || []).join(", ") || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
