"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { rest, setToken } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [error, setError] = useState("");

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    try {
      const data = await rest<{ access: string }>("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({
          tenant: form.get("tenant"),
          email: form.get("email"),
          password: form.get("password"),
        }),
      });
      setToken(data.access);
      router.replace("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    }
  }

  return (
    <form className="login" onSubmit={onSubmit}>
      <h2>FleetIQ ops</h2>
      <p className="muted">Phase B · GraphQL dashboard over tenant JWT</p>
      <label>Tenant</label>
      <input name="tenant" defaultValue="acme-logistics" />
      <label>Email</label>
      <input name="email" defaultValue="ops@acme-logistics.example" />
      <label>Password</label>
      <input name="password" type="password" defaultValue="password" />
      {error ? <p className="err">{error}</p> : null}
      <button type="submit">Sign in</button>
    </form>
  );
}
