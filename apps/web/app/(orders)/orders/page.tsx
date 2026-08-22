"use client";

import Link from "next/link";

import { useOrdersQuery } from "@/lib/queries";
import { sanitizeText } from "@/lib/sanitize";

export default function OrdersPage() {
  const { data: rows = [], error } = useOrdersQuery();
  return (
    <>
      <h2>Orders</h2>
      {error ? <p className="err">{sanitizeText(error.message, 200)}</p> : null}
      <table>
        <thead>
          <tr>
            <th>Number</th>
            <th>Customer</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((o) => (
            <tr key={o.id}>
              <td>
                <Link href={`/orders/${o.id}`}>{sanitizeText(o.orderNumber, 64)}</Link>
              </td>
              <td>{sanitizeText(o.customer?.name, 120)}</td>
              <td>{sanitizeText(o.status, 32)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
