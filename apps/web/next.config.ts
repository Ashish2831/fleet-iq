import type { NextConfig } from "next";

const fleet = process.env.FLEET_MFE_ORIGIN;
const orders = process.env.ORDERS_MFE_ORIGIN;

const nextConfig: NextConfig = {
  reactStrictMode: true,
  transpilePackages: ["@fleetiq/sanitize"],
  async rewrites() {
    const rules = [];
    if (fleet) {
      rules.push(
        { source: "/live-map", destination: `${fleet}/live-map` },
        { source: "/vehicles", destination: `${fleet}/vehicles` },
        { source: "/drivers", destination: `${fleet}/drivers` },
      );
    }
    if (orders) {
      rules.push(
        { source: "/orders", destination: `${orders}/orders` },
        { source: "/orders/:path*", destination: `${orders}/orders/:path*` },
        { source: "/shipments", destination: `${orders}/shipments` },
      );
    }
    return rules;
  },
};

export default nextConfig;
