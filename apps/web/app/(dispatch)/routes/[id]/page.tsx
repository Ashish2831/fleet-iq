"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { gql } from "@/lib/api";

export default function RouteDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [route, setRoute] = useState<any>(null);
  useEffect(() => {
    gql<{ route: any }>(
      `query ($id: ID!) {
        route(id: $id) {
          routeNumber status plannedDate
          assignment { driverName vehiclePlate }
          stops { sequence stopType status address { city line1 } }
        }
      }`,
      { id }
    ).then((d) => setRoute(d.route));
  }, [id]);
  if (!route) return <p className="muted">Loading…</p>;
  return (
    <>
      <h2>{route.routeNumber}</h2>
      <p className="muted">
        {route.status} · {route.assignment?.driverName} · {route.assignment?.vehiclePlate}
      </p>
      <table>
        <thead><tr><th>#</th><th>Type</th><th>Address</th><th>Status</th></tr></thead>
        <tbody>
          {route.stops.map((s: any) => (
            <tr key={s.sequence}>
              <td>{s.sequence}</td>
              <td>{s.stopType}</td>
              <td>{s.address.line1}, {s.address.city}</td>
              <td>{s.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
