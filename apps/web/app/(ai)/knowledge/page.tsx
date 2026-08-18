"use client";

import { useState } from "react";
import { rest } from "@/lib/api";

type Hit = { text: string; title: string; source: string; heading: string; page?: number; score: number };

export default function KnowledgePage() {
  const [q, setQ] = useState("late delivery promised_at");
  const [hits, setHits] = useState<Hit[]>([]);
  const [err, setErr] = useState("");

  async function search() {
    setErr("");
    try {
      const data = await rest<{ hits: Hit[] }>("/api/v1/search/knowledge", {
        method: "POST",
        body: JSON.stringify({ q }),
      });
      setHits(data.hits || []);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Search failed");
    }
  }

  return (
    <>
      <h2>Knowledge</h2>
      <p className="muted">Same hybrid SOP index the Operations agent cites. Postgres is not the RAG store.</p>
      <div style={{ display: "flex", gap: 8, margin: "16px 0" }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} style={{ minWidth: 320, padding: "8px 10px" }} />
        <button className="ghost" type="button" onClick={search}>
          Search
        </button>
      </div>
      {err ? <p className="err">{err}</p> : null}
      {hits.map((h) => (
        <div key={`${h.source}-${h.page}-${h.heading}`} className="card" style={{ marginBottom: 12 }}>
          <b style={{ fontSize: 16, color: "inherit" }}>
            {h.title} {h.page ? `· p.${h.page}` : ""}
          </b>
          <span>{h.heading}</span>
          <p>{h.text}</p>
          <p className="muted">{h.source}</p>
        </div>
      ))}
    </>
  );
}
