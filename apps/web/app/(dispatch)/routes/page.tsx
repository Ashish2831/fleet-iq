"use client";

import Link from "next/link";

import { useRoutesQuery } from "@/lib/queries";
import { sanitizeText } from "@/lib/sanitize";

export default function RoutesPage() {
  const { data: rows = [], error } = useRoutesQuery();
  return (
    <>
      <h2>Routes</h2>
      {error ? <p className="err">{error.message}</p> : null}
      <table>
        <thead>
          <tr>
            <th>Number</th>
            <th>Date</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>
                <Link href={`/routes/${r.id}`}>{sanitizeText(r.routeNumber, 64)}</Link>
              </td>
              <td>{sanitizeText(r.plannedDate, 32)}</td>
              <td>{sanitizeText(r.status, 32)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
