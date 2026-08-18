"use client";

import { useEffect, useState } from "react";
import { rest } from "@/lib/api";

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

export default function DispatchPage() {
  const [rows, setRows] = useState<Proposal[]>([]);
  const [err, setErr] = useState("");

  async function load() {
    try {
      const data = await rest<any>("/api/v1/dispatch/proposals/?status=pending");
      setRows(data.results || data);
    } catch (e: any) {
      setErr(e.message);
    }
  }

  useEffect(() => {
    load();
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, []);

  async function act(id: string, verb: "approve" | "reject") {
    setErr("");
    try {
      await rest(`/api/v1/dispatch/proposals/${id}/${verb}/`, { method: "POST" });
      await load();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  return (
    <>
      <h2>Dispatch queue</h2>
      <p className="muted">Solver scores drivers. Approve applies assign_route. The LLM does not pick vehicles.</p>
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
          {rows.map((p) => (
            <tr key={p.id}>
              <td>{p.order_number}</td>
              <td>{p.chosen?.driver_name || "—"}</td>
              <td>{p.chosen?.vehicle_plate || "—"}</td>
              <td>{p.score ?? "—"}</td>
              <td>{p.alternatives?.length || 0}</td>
              <td>
                <button className="ghost" type="button" onClick={() => act(p.id, "approve")}>
                  Approve
                </button>{" "}
                <button className="ghost" type="button" onClick={() => act(p.id, "reject")}>
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
