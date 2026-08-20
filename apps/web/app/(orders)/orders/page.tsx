"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { gql, sanitizeText } from "@/lib/api";

export default function OrdersPage() {
  const [rows, setRows] = useState<{ id: string; orderNumber: string; status: string; customer: { name: string } }[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    gql<{ orders: typeof rows }>(`query { orders(first: 50) { id orderNumber status customer { name } } }`)
      .then((d) => setRows(d.orders))
      .catch((e) => setError(sanitizeText(e instanceof Error ? e.message : "Failed", 200)));
  }, []);
  return (
    <>
      <h2>Orders</h2>
      {error ? <p className="err">{error}</p> : null}
      <table>
        <thead><tr><th>Number</th><th>Customer</th><th>Status</th></tr></thead>
        <tbody>
          {rows.map((o) => (
            <tr key={o.id}>
              <td><Link href={`/orders/${o.id}`}>{sanitizeText(o.orderNumber, 64)}</Link></td>
              <td>{sanitizeText(o.customer?.name, 120)}</td>
              <td>{sanitizeText(o.status, 32)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
