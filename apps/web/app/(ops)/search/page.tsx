"use client";

import { useState } from "react";
import { gql, rest } from "@/lib/api";

type ShipHit = {
  shipmentNumber: string;
  status: string;
  delayed: boolean;
  city: string;
  warehouseCode: string;
  customerName: string;
  score: number;
};

type KnowHit = { text: string; title: string; source: string; score: number; heading: string };

export default function SearchPage() {
  const [q, setQ] = useState("Whitefield");
  const [delayed, setDelayed] = useState(true);
  const [ships, setShips] = useState<ShipHit[]>([]);
  const [facets, setFacets] = useState<string[]>([]);
  const [knowledge, setKnowledge] = useState<KnowHit[]>([]);
  const [err, setErr] = useState("");

  async function run() {
    setErr("");
    try {
      const data = await gql<{
        searchShipments: { hits: ShipHit[]; facetsWarehouse: string[] };
        searchKnowledge: KnowHit[];
      }>(
        `query($q: String, $delayed: Boolean) {
          searchShipments(q: $q, delayed: $delayed, city: "Bengaluru") {
            hits { shipmentNumber status delayed city warehouseCode customerName score }
            facetsWarehouse
          }
          searchKnowledge(q: $q) { text title source score heading }
        }`,
        { q, delayed }
      );
      setShips(data.searchShipments.hits);
      setFacets(data.searchShipments.facetsWarehouse);
      setKnowledge(data.searchKnowledge);
    } catch (e: any) {
      setErr(e.message);
    }
  }

  return (
    <>
      <h2>Ops search</h2>
      <p className="muted">Elasticsearch projection. Postgres remains the source of truth.</p>
      <div style={{ display: "flex", gap: 8, margin: "16px 0", flexWrap: "wrap" }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} style={{ minWidth: 280, padding: "8px 10px" }} />
        <label className="muted" style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <input type="checkbox" checked={delayed} onChange={(e) => setDelayed(e.target.checked)} />
          Delayed
        </label>
        <button className="ghost" onClick={run} type="button">
          Search
        </button>
      </div>
      {err ? <p className="err">{err}</p> : null}
      {facets.length ? <p className="muted">Warehouses: {facets.join(", ")}</p> : null}
      <h3>Shipments</h3>
      <table>
        <thead>
          <tr>
            <th>Number</th>
            <th>Status</th>
            <th>City</th>
            <th>Warehouse</th>
            <th>Customer</th>
          </tr>
        </thead>
        <tbody>
          {ships.map((s) => (
            <tr key={s.shipmentNumber}>
              <td>{s.shipmentNumber}</td>
              <td>{s.delayed ? "delayed" : s.status}</td>
              <td>{s.city}</td>
              <td>{s.warehouseCode}</td>
              <td>{s.customerName}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h3>Knowledge</h3>
      {knowledge.map((k, i) => (
        <div key={i} className="card" style={{ marginBottom: 8 }}>
          <b>{k.title}</b>
          <span>
            {k.source} · {k.heading}
          </span>
          <p className="muted">{k.text.slice(0, 280)}</p>
        </div>
      ))}
    </>
  );
}
