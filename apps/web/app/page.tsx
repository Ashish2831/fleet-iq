"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { gql } from "@/lib/api";

type Dash = {
  dashboard: {
    activeVehicles: number;
    activeDrivers: number;
    delayedDeliveries: number;
    inTransitShipments: number;
    routes: { id: string; routeNumber: string; status: string; eta: string | null; driverName: string | null }[];
  };
};

export default function DashboardPage() {
  const [data, setData] = useState<Dash["dashboard"] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    gql<Dash>(`query {
      dashboard {
        activeVehicles delayedDeliveries activeDrivers inTransitShipments
        routes { id routeNumber status eta driverName }
      }
    }`)
      .then((d) => setData(d.dashboard))
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <p className="err">{error}</p>;
  if (!data) return <p className="muted">Loading…</p>;

  return (
    <>
      <h2>Live operations</h2>
      <div className="cards">
        <div className="card"><b>{data.activeVehicles}</b><span>Active vehicles</span></div>
        <div className="card"><b>{data.activeDrivers}</b><span>Active drivers</span></div>
        <div className="card"><b>{data.delayedDeliveries}</b><span>Delayed deliveries</span></div>
        <div className="card"><b>{data.inTransitShipments}</b><span>In transit</span></div>
      </div>
      <h3>Today’s routes</h3>
      <table>
        <thead><tr><th>Route</th><th>Status</th><th>Driver</th><th>ETA</th></tr></thead>
        <tbody>
          {data.routes.map((r) => (
            <tr key={r.id}>
              <td><Link href={`/routes/${r.id}`}>{r.routeNumber}</Link></td>
              <td>{r.status}</td>
              <td>{r.driverName ?? "—"}</td>
              <td>{r.eta ? new Date(r.eta).toLocaleTimeString() : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
