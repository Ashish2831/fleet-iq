"use client";

import { useState } from "react";
import { sanitizeText, useDeferredQuery } from "@/lib/api";
import { SearchService } from "@/lib/services";

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
  const { query: q, deferredQuery, setQuery, isPending } = useDeferredQuery("Whitefield");
  const [delayed, setDelayed] = useState(true);
  const [ships, setShips] = useState<ShipHit[]>([]);
  const [facets, setFacets] = useState<string[]>([]);
  const [knowledge, setKnowledge] = useState<KnowHit[]>([]);
  const [err, setErr] = useState("");

  async function run() {
    setErr("");
    try {
      const data = await SearchService.run(deferredQuery || q, delayed);
      setShips(data.searchShipments.hits);
      setFacets(data.searchShipments.facetsWarehouse);
      setKnowledge(data.searchKnowledge);
    } catch (e: unknown) {
      setErr(sanitizeText(e instanceof Error ? e.message : "Search failed", 200));
    }
  }

  return (
    <>
      <h2>Ops search</h2>
      <p className="muted">Elasticsearch projection. Postgres remains the source of truth.</p>
      <div style={{ display: "flex", gap: 8, margin: "16px 0", flexWrap: "wrap" }}>
        <input
          value={q}
          onChange={(e) => setQuery(e.target.value)}
          style={{ minWidth: 280, padding: "8px 10px" }}
          aria-busy={isPending}
        />
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
              <td>{sanitizeText(s.shipmentNumber, 64)}</td>
              <td>{s.delayed ? "delayed" : sanitizeText(s.status, 32)}</td>
              <td>{sanitizeText(s.city, 64)}</td>
              <td>{sanitizeText(s.warehouseCode, 32)}</td>
              <td>{sanitizeText(s.customerName, 120)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h3>Knowledge</h3>
      {knowledge.map((k, i) => (
        <div key={i} className="card" style={{ marginBottom: 8 }}>
          <b>{sanitizeText(k.title, 120)}</b>
          <span>
            {sanitizeText(k.source, 64)} · {sanitizeText(k.heading, 120)}
          </span>
          <p className="muted">{sanitizeText(k.text, 280)}</p>
        </div>
      ))}
    </>
  );
}
