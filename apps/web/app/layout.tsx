"use client";

import "./globals.css";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { clearToken, getToken } from "@/lib/api";

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

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (path !== "/login" && !getToken()) router.replace("/login");
    setReady(true);
  }, [path, router]);

  if (path === "/login") {
    return (
      <html lang="en">
        <body>
          <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;600&display=swap" />
          {children}
        </body>
      </html>
    );
  }

  return (
    <html lang="en">
      <body>
        <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;600&display=swap" />
        {ready ? (
          <div className="shell">
            <nav className="side">
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
        ) : null}
      </body>
    </html>
  );
}
