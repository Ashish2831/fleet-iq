"use client";

import { useState } from "react";
import Link from "next/link";
import { rest } from "@/lib/api";

type Source = { title?: string; heading?: string; source?: string; page?: number };
type Run = {
  id: string;
  agent: string;
  status: string;
  input: string;
  output: {
    summary?: string;
    delayed_count?: number | null;
    clusters?: string[];
    root_causes?: string[];
    recommended_actions?: string[];
    sources?: Source[];
    proposal_id?: string | null;
  };
  proposal_id: string | null;
  trace: { tool?: string; node?: string }[];
};

const PROMPTS = [
  "Why are deliveries delayed today?",
  "Why is shipment SHP-2001 delayed?",
  "Why are deliveries delayed today? Propose a reassignment.",
];

export default function AIAssistantPage() {
  const [q, setQ] = useState(PROMPTS[0]);
  const [run, setRun] = useState<Run | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function ask() {
    setErr("");
    setBusy(true);
    try {
      const data = await rest<Run>("/api/v1/ai/runs", {
        method: "POST",
        body: JSON.stringify({ agent: "operations", input: q }),
      });
      setRun(data);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }

  const out = run?.output || {};

  return (
    <>
      <h2>AI assistant</h2>
      <p className="muted">
        Operations agent. Numbers come from tools (Postgres, Redis, Mongo, ES). Mutations create a DispatchProposal.
      </p>
      <div style={{ display: "flex", gap: 8, margin: "16px 0", flexWrap: "wrap" }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} style={{ minWidth: 360, padding: "8px 10px" }} />
        <button className="ghost" type="button" onClick={ask} disabled={busy}>
          {busy ? "Running…" : "Ask"}
        </button>
      </div>
      <p className="muted">
        {PROMPTS.map((p) => (
          <button key={p} className="ghost" type="button" style={{ marginRight: 8 }} onClick={() => setQ(p)}>
            {p}
          </button>
        ))}
      </p>
      {err ? <p className="err">{err}</p> : null}
      {run ? (
        <div className="card" style={{ maxWidth: 720 }}>
          <p>
            <b>{out.delayed_count ?? "—"}</b>
            <span> delayed (from tools)</span>
          </p>
          <p>{out.summary}</p>
          {out.clusters?.length ? <p className="muted">Clusters: {out.clusters.join(", ")}</p> : null}
          {out.root_causes?.length ? <p className="muted">Causes: {out.root_causes.join(", ")}</p> : null}
          {out.recommended_actions?.length ? (
            <ul>
              {out.recommended_actions.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          ) : null}
          <p className="muted">
            Sources:{" "}
            {(out.sources || []).map((s) => (
              <span key={`${s.source}-${s.page}`} className="ghost" style={{ marginRight: 8, padding: "2px 8px" }}>
                {s.title || s.source} {s.page ? `p.${s.page}` : ""}
              </span>
            ))}
          </p>
          {run.proposal_id ? (
            <p>
              <Link href="/dispatch">Open dispatch proposal {run.proposal_id}</Link>
            </p>
          ) : null}
          <p className="muted">Tools: {(run.trace || []).map((t) => t.tool).filter(Boolean).join(" → ")}</p>
        </div>
      ) : null}
    </>
  );
}
