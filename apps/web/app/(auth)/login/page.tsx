"use client";

import { useActionState } from "react";
import { useRouter } from "next/navigation";

import { SubmitButton } from "@/lib/SubmitButton";
import { sanitizeText } from "@/lib/sanitize";
import { AuthService } from "@/lib/services";

export default function LoginPage() {
  const router = useRouter();
  const [error, formAction] = useActionState(async (_prev: string, form: FormData) => {
    try {
      await AuthService.login({
        tenant: String(form.get("tenant") || ""),
        email: String(form.get("email") || ""),
        password: String(form.get("password") || ""),
      });
      router.replace("/");
      return "";
    } catch (err) {
      return sanitizeText(err instanceof Error ? err.message : "Login failed", 200);
    }
  }, "");

  return (
    <form className="login" action={formAction}>
      <h2>FleetIQ ops</h2>
      <p className="muted">Phase B · GraphQL dashboard over tenant JWT</p>
      <label>Tenant</label>
      <input name="tenant" defaultValue="acme-logistics" />
      <label>Email</label>
      <input name="email" defaultValue="ops@acme-logistics.example" />
      <label>Password</label>
      <input name="password" type="password" defaultValue="password" />
      {error ? <p className="err">{error}</p> : null}
      <SubmitButton idle="Sign in" pending="Signing in…" />
    </form>
  );
}
