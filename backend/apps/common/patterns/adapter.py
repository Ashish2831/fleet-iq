"""Adapters — REST vs GraphQL payload shapes for the same domain reads."""

from __future__ import annotations

from abc import ABC, abstractmethod

from apps.common.repositories import DriverRepository, VehicleRepository


class FleetReadAdapter(ABC):
    @abstractmethod
    def list_vehicles(self, *, status: str | None = None, limit: int = 50) -> list[dict]: ...

    @abstractmethod
    def list_drivers(self, *, status: str | None = None, limit: int = 50) -> list[dict]: ...


class RestFleetAdapter(FleetReadAdapter):
    """DRF-shaped keys (snake_case)."""

    def __init__(self, tenant):
        self.tenant = tenant

    def list_vehicles(self, *, status: str | None = None, limit: int = 50) -> list[dict]:
        qs = VehicleRepository(self.tenant).qs()
        if status:
            qs = qs.filter(status=status)
        return [
            {
                "id": str(v.id),
                "plate_number": v.plate_number,
                "status": v.status,
                "make": v.make,
                "vehicle_type_name": v.vehicle_type.name if getattr(v, "vehicle_type", None) else "",
            }
            for v in qs.order_by("plate_number")[:limit]
        ]

    def list_drivers(self, *, status: str | None = None, limit: int = 50) -> list[dict]:
        qs = DriverRepository(self.tenant).qs()
        if status:
            qs = qs.filter(status=status)
        return [
            {
                "id": str(d.id),
                "employee_code": d.employee_code,
                "full_name": d.full_name,
                "status": d.status,
                "skills": list(d.skills or []),
            }
            for d in qs.order_by("employee_code")[:limit]
        ]


class GraphQLFleetAdapter(RestFleetAdapter):
    """GraphQL-shaped keys (camelCase) for gateway/MFE consumers."""

    def list_vehicles(self, *, status: str | None = None, limit: int = 50) -> list[dict]:
        return [
            {
                "id": row["id"],
                "plateNumber": row["plate_number"],
                "status": row["status"],
                "make": row["make"],
                "vehicleTypeName": row["vehicle_type_name"],
            }
            for row in super().list_vehicles(status=status, limit=limit)
        ]

    def list_drivers(self, *, status: str | None = None, limit: int = 50) -> list[dict]:
        return [
            {
                "id": row["id"],
                "employeeCode": row["employee_code"],
                "fullName": row["full_name"],
                "status": row["status"],
                "skills": row["skills"],
            }
            for row in super().list_drivers(status=status, limit=limit)
        ]
