"use client";

import { useEffect, useState } from "react";
import { rest } from "@fleetiq/gql-client";
import { sanitizeText } from "@fleetiq/sanitize";

type Proposal = { id: string; order_number: string; status: string };

export default function Page() {
  const [rows, setRows] = useState<Proposal[]>([]);

  useEffect(() => {
    rest<{ results?: Proposal[] } | Proposal[]>("/api/v1/dispatch/proposals/?status=pending").then((data) =>
      setRows(Array.isArray(data) ? data : data.results || []),
    );
  }, []);

  return (
    <main>
      <h2>{sanitizeText("Dispatch remote")}</h2>
      <ul>
        {rows.map((p) => (
          <li key={p.id}>
            {sanitizeText(p.order_number)} · {sanitizeText(p.status)}
          </li>
        ))}
      </ul>
    </main>
  );
}
