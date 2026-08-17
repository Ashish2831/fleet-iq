"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { gql } from "@/lib/api";

export default function OrdersPage() {
  const [rows, setRows] = useState<{ id: string; orderNumber: string; status: string; customer: { name: string } }[]>([]);
  useEffect(() => {
    gql<{ orders: typeof rows }>(`query { orders(first: 50) { id orderNumber status customer { name } } }`).then((d) =>
      setRows(d.orders)
    );
  }, []);
  return (
    <>
      <h2>Orders</h2>
      <table>
        <thead><tr><th>Number</th><th>Customer</th><th>Status</th></tr></thead>
        <tbody>
          {rows.map((o) => (
            <tr key={o.id}>
              <td><Link href={`/orders/${o.id}`}>{o.orderNumber}</Link></td>
              <td>{o.customer.name}</td>
              <td>{o.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
