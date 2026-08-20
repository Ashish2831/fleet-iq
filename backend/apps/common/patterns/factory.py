"""Factory — construct repositories / strategies without hard-coding call sites."""

from __future__ import annotations

from apps.common.patterns.rate_limit import CacheRateLimitStore, MemoryRateLimitStore, RateLimitStore
from apps.common.repositories import (
    AddressRepository,
    CustomerRepository,
    DeliveryRepository,
    DispatchProposalRepository,
    DriverRepository,
    OrderRepository,
    RouteRepository,
    ShipmentRepository,
    VehicleRepository,
    WarehouseRepository,
)
from apps.events.bus import EventBus, get_bus


class ServiceFactory:
    @staticmethod
    def orders(tenant) -> OrderRepository:
        return OrderRepository(tenant)

    @staticmethod
    def vehicles(tenant) -> VehicleRepository:
        return VehicleRepository(tenant)

    @staticmethod
    def drivers(tenant) -> DriverRepository:
        return DriverRepository(tenant)

    @staticmethod
    def shipments(tenant) -> ShipmentRepository:
        return ShipmentRepository(tenant)

    @staticmethod
    def deliveries(tenant) -> DeliveryRepository:
        return DeliveryRepository(tenant)

    @staticmethod
    def routes(tenant) -> RouteRepository:
        return RouteRepository(tenant)

    @staticmethod
    def proposals(tenant) -> DispatchProposalRepository:
        return DispatchProposalRepository(tenant)

    @staticmethod
    def customers(tenant) -> CustomerRepository:
        return CustomerRepository(tenant)

    @staticmethod
    def warehouses(tenant) -> WarehouseRepository:
        return WarehouseRepository(tenant)

    @staticmethod
    def addresses(tenant) -> AddressRepository:
        return AddressRepository(tenant)

    @staticmethod
    def bus() -> EventBus:
        return get_bus()

    @staticmethod
    def rate_limit_store(*, prefer_cache: bool = True) -> RateLimitStore:
        if prefer_cache:
            try:
                from django.core.cache import cache

                cache.get("fleetiq-rl-probe")
                return CacheRateLimitStore()
            except Exception:
                return MemoryRateLimitStore()
        return MemoryRateLimitStore()
