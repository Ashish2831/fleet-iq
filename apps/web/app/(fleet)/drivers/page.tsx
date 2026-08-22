"use client";

import { useDriversQuery } from "@/lib/queries";
import { sanitizeText } from "@/lib/sanitize";

export default function DriversPage() {
  const { data: rows = [], error } = useDriversQuery();
  return (
    <>
      <h2>Drivers</h2>
      {error ? <p className="err">{sanitizeText(error.message, 200)}</p> : null}
      <table>
        <thead>
          <tr>
            <th>Code</th>
            <th>Name</th>
            <th>Status</th>
            <th>Skills</th>
          </tr>
        </thead>
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
