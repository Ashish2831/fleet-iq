"use client";

import { useEffect, useState } from "react";
import { rest, sanitizeText } from "@/lib/api";

const AGENTS = [
  { id: "operations", title: "Operations", blurb: "Why delayed? Tools over Postgres, Redis, Mongo, ES. May propose reassignment." },
  { id: "dispatch_explain", title: "Dispatch explainer", blurb: "Reads DispatchProposal. Does not run the solver." },
  { id: "route_risk", title: "Route risk", blurb: "ETA risk. Enqueues reoptimization; does not edit stops." },
  { id: "maintenance", title: "Maintenance", blurb: "Opens a stub ticket and VehicleMaintenanceDue outbox event." },
];

type Run = { id: string; agent: string; status: string; input: string; created_at: string };

export default function AgentsPage() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [err, setErr] = useState("");

  useEffect(() => {
    rest<Run[]>("/api/v1/ai/runs")
      .then(setRuns)
      .catch((e) => setErr(sanitizeText(e instanceof Error ? e.message : "Failed", 200)));
  }, []);

  return (
    <>
      <h2>Agents</h2>
      <p className="muted">Four graphs, one gateway. Tenant comes from JWT, never from the prompt.</p>
      {err ? <p className="err">{err}</p> : null}
      <div className="cards" style={{ gridTemplateColumns: "repeat(2, 1fr)" }}>
        {AGENTS.map((a) => {
          const last = runs.find((r) => r.agent === a.id);
          return (
            <div key={a.id} className="card">
              <b style={{ fontSize: 18, color: "inherit" }}>{a.title}</b>
              <span>{a.blurb}</span>
              <p className="muted" style={{ marginTop: 12 }}>
                Last:{" "}
                {last
                  ? `${sanitizeText(last.status, 32)} — ${sanitizeText(last.input, 48)}`
                  : "no runs yet"}
              </p>
            </div>
          );
        })}
      </div>
    </>
  );
}
