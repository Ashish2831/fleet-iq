"use client";

import Link from "next/link";

import { useDashboardQuery } from "@/lib/queries";
import { sanitizeText } from "@/lib/sanitize";

export default function DashboardPage() {
  const { data, error, isLoading } = useDashboardQuery();

  if (error) return <p className="err">{sanitizeText(error.message, 200)}</p>;
  if (isLoading || !data) return <p className="muted">Loading…</p>;

  return (
    <>
      <h2>Live operations</h2>
      <div className="cards">
        <div className="card">
          <b>{data.activeVehicles}</b>
          <span>Active vehicles</span>
        </div>
        <div className="card">
          <b>{data.activeDrivers}</b>
          <span>Active drivers</span>
        </div>
        <div className="card">
          <b>{data.delayedDeliveries}</b>
          <span>Delayed deliveries</span>
        </div>
        <div className="card">
          <b>{data.inTransitShipments}</b>
          <span>In transit</span>
        </div>
      </div>
      <h3>Today’s routes</h3>
      <table>
        <thead>
          <tr>
            <th>Route</th>
            <th>Status</th>
            <th>Driver</th>
            <th>ETA</th>
          </tr>
        </thead>
        <tbody>
          {data.routes.map((r) => (
            <tr key={r.id}>
              <td>
                <Link href={`/routes/${r.id}`}>{sanitizeText(r.routeNumber, 64)}</Link>
              </td>
              <td>{sanitizeText(r.status, 32)}</td>
              <td>{sanitizeText(r.driverName ?? "—", 64)}</td>
              <td>{r.eta ? new Date(r.eta).toLocaleTimeString() : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
