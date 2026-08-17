"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { gql } from "@/lib/api";

export default function RoutesPage() {
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => {
    gql<{ routes: any[] }>(`query { routes { id routeNumber status plannedDate } }`).then((d) => setRows(d.routes));
  }, []);
  return (
    <>
      <h2>Routes</h2>
      <table>
        <thead><tr><th>Number</th><th>Date</th><th>Status</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td><Link href={`/routes/${r.id}`}>{r.routeNumber}</Link></td>
              <td>{r.plannedDate}</td>
              <td>{r.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
