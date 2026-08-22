/** Thin domain services — React Query hooks call these, not fetch directly. */

import { fleetAdapter, type Driver, type Vehicle } from "../adapters";
import { gql, rest } from "../client";
import { setToken } from "../auth";
import { sanitizeText } from "../sanitize";

export class AuthService {
  static async login(input: { tenant: string; email: string; password: string }) {
    const data = await rest<{ access: string; user?: { email: string; full_name: string; tenant_slug: string } }>(
      "/api/v1/auth/login",
      {
        method: "POST",
        dedupe: false,
        useHttpCache: false,
        body: JSON.stringify(input),
      },
    );
    setToken(data.access);
    return data;
  }
}

export class FleetService {
  constructor(private adapter = fleetAdapter) {}

  listVehicles() {
    return this.adapter.listVehicles();
  }

  listDrivers() {
    return this.adapter.listDrivers();
  }
}

export class DashboardService {
  static async load() {
    const data = await gql<{
      dashboard: {
        activeVehicles: number;
        activeDrivers: number;
        delayedDeliveries: number;
        inTransitShipments: number;
        routes: { id: string; routeNumber: string; status: string; eta: string | null; driverName: string | null }[];
      };
    }>(`query {
      dashboard {
        activeVehicles delayedDeliveries activeDrivers inTransitShipments
        routes { id routeNumber status eta driverName }
      }
    }`);
    return data.dashboard;
  }
}

export class OrderService {
  static async list() {
    const data = await gql<{
      orders: { id: string; orderNumber: string; status: string; customer: { name: string } }[];
    }>(`query { orders(first: 50) { id orderNumber status customer { name } } }`);
    return data.orders;
  }
}

export class ShipmentService {
  static async list() {
    const data = await gql<{
      shipments: { id: string; shipmentNumber: string; status: string; promisedAt?: string | null }[];
    }>(`query { shipments { id shipmentNumber status promisedAt } }`);
    return data.shipments;
  }
}

export class RouteService {
  static async list() {
    const data = await gql<{
      routes: { id: string; routeNumber: string; status: string; plannedDate: string }[];
    }>(`query { routes { id routeNumber status plannedDate } }`);
    return data.routes;
  }
}

export class SearchService {
  static async run(q: string, delayed: boolean) {
    return gql<{
      searchShipments: {
        hits: {
          shipmentNumber: string;
          status: string;
          delayed: boolean;
          city: string;
          warehouseCode: string;
          customerName: string;
          score: number;
        }[];
        facetsWarehouse: string[];
      };
      searchKnowledge: { text: string; title: string; source: string; score: number; heading: string }[];
    }>(
      `query($q: String, $delayed: Boolean) {
          searchShipments(q: $q, delayed: $delayed, city: "Bengaluru") {
            hits { shipmentNumber status delayed city warehouseCode customerName score }
            facetsWarehouse
          }
          searchKnowledge(q: $q) { text title source score heading }
        }`,
      { q, delayed },
    );
  }
}

export type DispatchProposal = {
  id: string;
  order_number: string;
  status: string;
  score: number | null;
  hard_pass: boolean;
  chosen: { driver_name?: string; vehicle_plate?: string; cost?: number; features?: Record<string, number> };
  alternatives: { driver_name?: string; cost?: number }[];
  explanation: { rejects?: unknown[] };
};

export class DispatchService {
  static async listPending(): Promise<DispatchProposal[]> {
    const data = await rest<{ results?: DispatchProposal[] } | DispatchProposal[]>(
      "/api/v1/dispatch/proposals/?status=pending",
      { useHttpCache: false },
    );
    return Array.isArray(data) ? data : data.results || [];
  }

  static async act(id: string, verb: "approve" | "reject") {
    return rest(`/api/v1/dispatch/proposals/${id}/${verb}/`, { method: "POST", dedupe: false, useHttpCache: false });
  }
}

export { sanitizeText };
export type { Driver, Vehicle };

export const fleetService = new FleetService();
