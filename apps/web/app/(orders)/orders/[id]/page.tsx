"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { gql, sanitizeText } from "@/lib/api";

export default function OrderDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [order, setOrder] = useState<any>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    gql<{ order: any }>(
      `query ($id: ID!) {
        order(id: $id) {
          orderNumber status deadlineAt
          customer { name }
          warehouse { code name }
          items { sku description quantity weightKg }
          shipments { shipmentNumber status promisedAt }
        }
      }`,
      { id },
    )
      .then((d) => setOrder(d.order))
      .catch((e) => setError(sanitizeText(e instanceof Error ? e.message : "Failed", 200)));
  }, [id]);
  if (error) return <p className="err">{error}</p>;
  if (!order) return <p className="muted">Loading…</p>;
  return (
    <>
      <h2>{sanitizeText(order.orderNumber, 64)}</h2>
      <p className="muted">
        {sanitizeText(order.status, 32)} · {sanitizeText(order.customer?.name, 120)} ·{" "}
        {sanitizeText(order.warehouse?.code, 32)}
      </p>
      <h3>Items</h3>
      <table>
        <thead><tr><th>SKU</th><th>Qty</th><th>Kg</th></tr></thead>
        <tbody>
          {order.items.map((i: any) => (
            <tr key={i.sku}>
              <td>{sanitizeText(i.sku, 64)}</td>
              <td>{i.quantity}</td>
              <td>{i.weightKg}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h3>Shipments</h3>
      <ul>
        {order.shipments.map((s: any) => (
          <li key={s.shipmentNumber}>
            {sanitizeText(s.shipmentNumber, 64)} — {sanitizeText(s.status, 32)}
          </li>
        ))}
      </ul>
    </>
  );
}
