"use client";

import { useState } from "react";
import Link from "next/link";
import { rest, sanitizeText, useDeferredQuery } from "@/lib/api";

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
  const { query: q, deferredQuery, setQuery, isPending } = useDeferredQuery(PROMPTS[0]);
  const [run, setRun] = useState<Run | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function ask() {
    setErr("");
    setBusy(true);
    try {
      const data = await rest<Run>("/api/v1/ai/runs", {
        method: "POST",
        dedupe: false,
        body: JSON.stringify({ agent: "operations", input: deferredQuery || q }),
      });
      setRun(data);
    } catch (e: unknown) {
      setErr(sanitizeText(e instanceof Error ? e.message : "Request failed", 200));
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
        <input
          value={q}
          onChange={(e) => setQuery(e.target.value)}
          style={{ minWidth: 360, padding: "8px 10px" }}
          aria-busy={isPending}
        />
        <button className="ghost" type="button" onClick={ask} disabled={busy}>
          {busy ? "Running…" : "Ask"}
        </button>
      </div>
      <p className="muted">
        {PROMPTS.map((p) => (
          <button key={p} className="ghost" type="button" style={{ marginRight: 8 }} onClick={() => setQuery(p)}>
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
          {out.summary ? <p>{sanitizeText(out.summary, 800)}</p> : null}
          {(out.root_causes || []).length ? (
            <ul>
              {out.root_causes!.map((c) => (
                <li key={c}>{sanitizeText(c, 200)}</li>
              ))}
            </ul>
          ) : null}
          {(out.recommended_actions || []).length ? (
            <ul>
              {out.recommended_actions!.map((a) => (
                <li key={a}>{sanitizeText(a, 200)}</li>
              ))}
            </ul>
          ) : null}
          {(out.sources || []).map((s, i) => (
            <p key={i} className="muted">
              {sanitizeText(s.title, 120)} · {sanitizeText(s.heading, 120)} · {sanitizeText(s.source, 64)}
            </p>
          ))}
          {run.proposal_id ? (
            <p>
              <Link href="/dispatch">Open dispatch proposal {sanitizeText(run.proposal_id, 64)}</Link>
            </p>
          ) : null}
          <p className="muted">
            Tools: {(run.trace || []).map((t) => sanitizeText(t.tool, 64)).filter(Boolean).join(" → ")}
          </p>
        </div>
      ) : null}
    </>
  );
}
