"use client";

import { useEffect, useOptimistic, useState, useTransition } from "react";
import { rest, sanitizeText } from "@/lib/api";

type Proposal = {
  id: string;
  order_number: string;
  status: string;
  score: number | null;
  hard_pass: boolean;
  chosen: { driver_name?: string; vehicle_plate?: string; cost?: number; features?: Record<string, number> };
  alternatives: { driver_name?: string; cost?: number }[];
  explanation: { rejects?: unknown[] };
};

type OptimisticAction = { id: string; status: "approved" | "rejected" };

export default function DispatchPage() {
  const [rows, setRows] = useState<Proposal[]>([]);
  const [err, setErr] = useState("");
  const [isPending, startTransition] = useTransition();
  const [optimisticRows, applyOptimistic] = useOptimistic(
    rows,
    (current, action: OptimisticAction) =>
      current.map((p) => (p.id === action.id ? { ...p, status: action.status } : p)),
  );

  async function load() {
    try {
      const data = await rest<{ results?: Proposal[] } | Proposal[]>(
        "/api/v1/dispatch/proposals/?status=pending",
      );
      setRows(Array.isArray(data) ? data : data.results || []);
      setErr("");
    } catch (e: unknown) {
      setErr(sanitizeText(e instanceof Error ? e.message : "Load failed", 200));
    }
  }

  useEffect(() => {
    load();
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, []);

  function act(id: string, verb: "approve" | "reject") {
    setErr("");
    const nextStatus = verb === "approve" ? "approved" : "rejected";
    startTransition(async () => {
      applyOptimistic({ id, status: nextStatus });
      try {
        await rest(`/api/v1/dispatch/proposals/${id}/${verb}/`, { method: "POST", dedupe: false });
        await load();
      } catch (e: unknown) {
        setErr(sanitizeText(e instanceof Error ? e.message : "Action failed", 200));
        await load();
      }
    });
  }

  const visible = optimisticRows.filter((p) => p.status === "pending");

  return (
    <>
      <h2>Dispatch queue</h2>
      <p className="muted">
        Solver scores drivers. Approve applies assign_route. The LLM does not pick vehicles.
        {isPending ? " Updating…" : ""}
      </p>
      {err ? <p className="err">{err}</p> : null}
      <table>
        <thead>
          <tr>
            <th>Order</th>
            <th>Driver</th>
            <th>Vehicle</th>
            <th>Cost</th>
            <th>Alts</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {visible.map((p) => (
            <tr key={p.id}>
              <td>{sanitizeText(p.order_number, 64)}</td>
              <td>{sanitizeText(p.chosen?.driver_name || "—", 64)}</td>
              <td>{sanitizeText(p.chosen?.vehicle_plate || "—", 32)}</td>
              <td>{p.score ?? "—"}</td>
              <td>{p.alternatives?.length || 0}</td>
              <td>
                <button className="ghost" type="button" disabled={isPending} onClick={() => act(p.id, "approve")}>
                  Approve
                </button>{" "}
                <button className="ghost" type="button" disabled={isPending} onClick={() => act(p.id, "reject")}>
                  Reject
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
