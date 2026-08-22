"use client";

import { useQuery } from "@tanstack/react-query";

import {
  DashboardService,
  DispatchService,
  fleetService,
  OrderService,
  RouteService,
  ShipmentService,
} from "./services";

export function useDashboardQuery() {
  return useQuery({ queryKey: ["dashboard"], queryFn: () => DashboardService.load() });
}

export function useVehiclesQuery() {
  return useQuery({ queryKey: ["vehicles"], queryFn: () => fleetService.listVehicles() });
}

export function useDriversQuery() {
  return useQuery({ queryKey: ["drivers"], queryFn: () => fleetService.listDrivers() });
}

export function useOrdersQuery() {
  return useQuery({ queryKey: ["orders"], queryFn: () => OrderService.list() });
}

export function useDispatchQueueQuery() {
  return useQuery({
    queryKey: ["dispatch-pending"],
    queryFn: () => DispatchService.listPending(),
    refetchInterval: 4000,
  });
}

export function useShipmentsQuery() {
  return useQuery({ queryKey: ["shipments"], queryFn: () => ShipmentService.list() });
}

export function useRoutesQuery() {
  return useQuery({ queryKey: ["routes"], queryFn: () => RouteService.list() });
}
