"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useOptimistic, useState, useTransition } from "react";

import { useDispatchQueueQuery } from "@/lib/queries";
import { sanitizeText } from "@/lib/sanitize";
import { DispatchService, type DispatchProposal } from "@/lib/services";

type OptimisticAction = { id: string; status: "approved" | "rejected" };

export default function DispatchPage() {
  const query = useDispatchQueueQuery();
  const rows = query.data ?? [];
  const queryClient = useQueryClient();
  const [err, setErr] = useState("");
  const [isPending, startTransition] = useTransition();
  const [optimisticRows, applyOptimistic] = useOptimistic(
    rows,
    (current, action: OptimisticAction) =>
      current.map((p) => (p.id === action.id ? { ...p, status: action.status } : p)),
  );

  const mutation = useMutation({
    mutationFn: ({ id, verb }: { id: string; verb: "approve" | "reject" }) => DispatchService.act(id, verb),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["dispatch-pending"] }),
  });

  function act(id: string, verb: "approve" | "reject") {
    setErr("");
    const nextStatus = verb === "approve" ? "approved" : "rejected";
    startTransition(async () => {
      applyOptimistic({ id, status: nextStatus });
      try {
        await mutation.mutateAsync({ id, verb });
      } catch (e: unknown) {
        setErr(sanitizeText(e instanceof Error ? e.message : "Action failed", 200));
      }
    });
  }

  const visible = (optimisticRows as DispatchProposal[]).filter((p) => p.status === "pending");

  return (
    <>
      <h2>Dispatch queue</h2>
      <p className="muted">
        Solver scores drivers. Approve applies assign_route. The LLM does not pick vehicles.
        {isPending ? " Updating…" : ""}
      </p>
      {err ? <p className="err">{err}</p> : null}
      {query.error ? <p className="err">{sanitizeText(query.error.message, 200)}</p> : null}
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
