import type { NextConfig } from "next";

const fleet = process.env.FLEET_MFE_ORIGIN;
const orders = process.env.ORDERS_MFE_ORIGIN;
const dispatch = process.env.DISPATCH_MFE_ORIGIN;
const ai = process.env.AI_MFE_ORIGIN;
const analytics = process.env.ANALYTICS_MFE_ORIGIN;

const nextConfig: NextConfig = {
  reactStrictMode: true,
  transpilePackages: ["@fleetiq/sanitize", "@fleetiq/gql-client"],
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
    if (dispatch) {
      rules.push({ source: "/dispatch", destination: `${dispatch}/` });
    }
    if (ai) {
      rules.push({ source: "/ai-assistant", destination: `${ai}/` });
    }
    if (analytics) {
      rules.push({ source: "/analytics", destination: `${analytics}/` });
    }
    return rules;
  },
};

export default nextConfig;
