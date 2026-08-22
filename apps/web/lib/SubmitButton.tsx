"use client";

import { useFormStatus } from "react-dom";

export function SubmitButton({ idle, pending }: { idle: string; pending: string }) {
  const { pending: busy } = useFormStatus();
  return (
    <button type="submit" disabled={busy}>
      {busy ? pending : idle}
    </button>
  );
}
