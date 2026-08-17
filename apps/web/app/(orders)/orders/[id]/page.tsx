"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { gql } from "@/lib/api";

export default function OrderDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [order, setOrder] = useState<any>(null);
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
      { id }
    ).then((d) => setOrder(d.order));
  }, [id]);
  if (!order) return <p className="muted">Loading…</p>;
  return (
    <>
      <h2>{order.orderNumber}</h2>
      <p className="muted">{order.status} · {order.customer.name} · {order.warehouse.code}</p>
      <h3>Items</h3>
      <table>
        <thead><tr><th>SKU</th><th>Qty</th><th>Kg</th></tr></thead>
        <tbody>
          {order.items.map((i: any) => (
            <tr key={i.sku}><td>{i.sku}</td><td>{i.quantity}</td><td>{i.weightKg}</td></tr>
          ))}
        </tbody>
      </table>
      <h3>Shipments</h3>
      <ul>
        {order.shipments.map((s: any) => (
          <li key={s.shipmentNumber}>{s.shipmentNumber} — {s.status}</li>
        ))}
      </ul>
    </>
  );
}
