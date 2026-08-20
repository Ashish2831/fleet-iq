"use client";

import { FormEvent, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { rest, sanitizeText, setToken } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [isPending, startTransition] = useTransition();

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    setError("");
    startTransition(async () => {
      try {
        const data = await rest<{ access: string }>("/api/v1/auth/login", {
          method: "POST",
          dedupe: false,
          body: JSON.stringify({
            tenant: form.get("tenant"),
            email: form.get("email"),
            password: form.get("password"),
          }),
        });
        setToken(data.access);
        router.replace("/");
      } catch (err) {
        setError(sanitizeText(err instanceof Error ? err.message : "Login failed", 200));
      }
    });
  }

  return (
    <form className="login" onSubmit={onSubmit}>
      <h2>FleetIQ ops</h2>
      <p className="muted">Phase B · GraphQL dashboard over tenant JWT</p>
      <label>Tenant</label>
      <input name="tenant" defaultValue="acme-logistics" disabled={isPending} />
      <label>Email</label>
      <input name="email" defaultValue="ops@acme-logistics.example" disabled={isPending} />
      <label>Password</label>
      <input name="password" type="password" defaultValue="password" disabled={isPending} />
      {error ? <p className="err">{error}</p> : null}
      <button type="submit" disabled={isPending}>
        {isPending ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}
