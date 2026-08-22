"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { clearToken } from "@/lib/api";
import { useAuthToken } from "@/lib/hooks/useAuthToken";
import { AppProviders } from "@/lib/providers";
import { selectSidebarCollapsed, useUiStore } from "@/lib/stores/ui";

import "./globals.css";

const links = [
  ["/", "Dashboard"],
  ["/orders", "Orders"],
  ["/shipments", "Shipments"],
  ["/drivers", "Drivers"],
  ["/vehicles", "Vehicles"],
  ["/live-map", "Live map"],
  ["/routes", "Routes"],
  ["/search", "Search"],
  ["/dispatch", "Dispatch"],
  ["/analytics", "Analytics"],
  ["/ai-assistant", "AI"],
  ["/agents", "Agents"],
  ["/knowledge", "Knowledge"],
];

function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const token = useAuthToken();
  const collapsed = useUiStore(selectSidebarCollapsed);

  useEffect(() => {
    if (path !== "/login" && !token) router.replace("/login");
  }, [path, router, token]);

  if (path === "/login") return <>{children}</>;
  if (!token) return null;

  return (
    <div className="shell">
      <nav className="side" data-collapsed={collapsed ? "true" : "false"}>
        <h1>FLEETIQ</h1>
        {links.map(([href, label]) => (
          <Link key={href} href={href} className={path === href ? "active" : ""}>
            {label}
          </Link>
        ))}
        <button
          style={{ marginTop: 24, background: "transparent", color: "#8a9a8c", border: 0, cursor: "pointer" }}
          onClick={() => {
            clearToken();
            router.push("/login");
          }}
        >
          Sign out
        </button>
      </nav>
      <main>{children}</main>
    </div>
  );
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;600&display=swap" />
        <AppProviders>
          <Shell>{children}</Shell>
        </AppProviders>
      </body>
    </html>
  );
}
