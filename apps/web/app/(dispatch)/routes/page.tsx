"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { gql, sanitizeText } from "@/lib/api";

type RouteRow = { id: string; routeNumber: string; status: string; plannedDate: string };

export default function RoutesPage() {
  const [rows, setRows] = useState<RouteRow[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    gql<{ routes: RouteRow[] }>(`query { routes { id routeNumber status plannedDate } }`)
      .then((d) => setRows(d.routes))
      .catch((e) => setError(sanitizeText(e instanceof Error ? e.message : "Failed", 200)));
  }, []);
  return (
    <>
      <h2>Routes</h2>
      {error ? <p className="err">{error}</p> : null}
      <table>
        <thead><tr><th>Number</th><th>Date</th><th>Status</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td><Link href={`/routes/${r.id}`}>{sanitizeText(r.routeNumber, 64)}</Link></td>
              <td>{sanitizeText(r.plannedDate, 32)}</td>
              <td>{sanitizeText(r.status, 32)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
