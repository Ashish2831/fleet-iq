/** Adapter pattern — REST vs GraphQL list shapes. */

import { gql, rest } from "./client";

export type Vehicle = {
  id: string;
  plateNumber: string;
  status: string;
  make?: string;
  vehicleTypeName?: string;
};

export type Driver = {
  id: string;
  employeeCode: string;
  fullName: string;
  status: string;
  skills: string[];
  rating?: number | null;
};

export interface FleetAdapter {
  listVehicles(): Promise<Vehicle[]>;
  listDrivers(): Promise<Driver[]>;
}

export class GraphQLFleetAdapter implements FleetAdapter {
  async listVehicles(): Promise<Vehicle[]> {
    const data = await gql<{ vehicles: Vehicle[] }>(
      `query { vehicles { id plateNumber status make vehicleTypeName } }`,
    );
    return data.vehicles;
  }

  async listDrivers(): Promise<Driver[]> {
    const data = await gql<{ drivers: Driver[] }>(
      `query { drivers { id employeeCode fullName status skills rating } }`,
    );
    return data.drivers;
  }
}

export class RestFleetAdapter implements FleetAdapter {
  async listVehicles(): Promise<Vehicle[]> {
    const data = await rest<{ results?: Array<Record<string, string>> } | Array<Record<string, string>>>(
      "/api/v1/vehicles/",
    );
    const rows = Array.isArray(data) ? data : data.results || [];
    return rows.map((v) => ({
      id: String(v.id),
      plateNumber: v.plate_number || v.plateNumber,
      status: v.status,
      make: v.make,
      vehicleTypeName: v.vehicle_type_name || v.vehicleTypeName,
    }));
  }

  async listDrivers(): Promise<Driver[]> {
    const data = await rest<{ results?: Array<Record<string, unknown>> } | Array<Record<string, unknown>>>(
      "/api/v1/drivers/",
    );
    const rows = Array.isArray(data) ? data : data.results || [];
    return rows.map((d) => ({
      id: String(d.id),
      employeeCode: String(d.employee_code || d.employeeCode || ""),
      fullName: String(d.full_name || d.fullName || ""),
      status: String(d.status || ""),
      skills: Array.isArray(d.skills) ? (d.skills as string[]) : [],
      rating: typeof d.rating === "number" ? d.rating : null,
    }));
  }
}

export const fleetAdapter: FleetAdapter = new GraphQLFleetAdapter();
