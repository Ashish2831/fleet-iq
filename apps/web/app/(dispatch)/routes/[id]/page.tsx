"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { gql, sanitizeText } from "@/lib/api";

export default function RouteDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [route, setRoute] = useState<any>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    gql<{ route: any }>(
      `query ($id: ID!) {
        route(id: $id) {
          routeNumber status plannedDate
          assignment { driverName vehiclePlate }
          stops { sequence stopType status address { city line1 } }
        }
      }`,
      { id },
    )
      .then((d) => setRoute(d.route))
      .catch((e) => setError(sanitizeText(e instanceof Error ? e.message : "Failed", 200)));
  }, [id]);
  if (error) return <p className="err">{error}</p>;
  if (!route) return <p className="muted">Loading…</p>;
  return (
    <>
      <h2>{sanitizeText(route.routeNumber, 64)}</h2>
      <p className="muted">
        {sanitizeText(route.status, 32)} · {sanitizeText(route.assignment?.driverName, 64)} ·{" "}
        {sanitizeText(route.assignment?.vehiclePlate, 32)}
      </p>
      <table>
        <thead><tr><th>#</th><th>Type</th><th>Address</th><th>Status</th></tr></thead>
        <tbody>
          {route.stops.map((s: any) => (
            <tr key={s.sequence}>
              <td>{s.sequence}</td>
              <td>{sanitizeText(s.stopType, 32)}</td>
              <td>
                {sanitizeText(s.address?.line1, 120)}, {sanitizeText(s.address?.city, 64)}
              </td>
              <td>{sanitizeText(s.status, 32)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
