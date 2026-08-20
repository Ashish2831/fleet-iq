from collections import defaultdict

from asgiref.sync import sync_to_async
from strawberry.dataloader import DataLoader

from apps.common.repositories import (
    AddressRepository,
    CustomerRepository,
    DeliveryRepository,
    DriverRepository,
    OrderItemRepository,
    RouteAssignmentRepository,
    RouteStopRepository,
    ShipmentItemRepository,
    ShipmentRepository,
    VehicleRepository,
    WarehouseRepository,
)


def _map(keys, rows, attr="id"):
    by_id = {str(getattr(row, attr)): row for row in rows}
    return [by_id.get(str(k)) for k in keys]


class Loaders:
    def __init__(self, tenant):
        self.tenant = tenant
        self.customer = DataLoader(self._customers)
        self.warehouse = DataLoader(self._warehouses)
        self.address = DataLoader(self._addresses)
        self.driver = DataLoader(self._drivers)
        self.vehicle = DataLoader(self._vehicles)
        self.items_by_order = DataLoader(self._items)
        self.stops_by_route = DataLoader(self._stops)
        self.assignment_by_route = DataLoader(self._assignments)
        self.shipments_by_order = DataLoader(self._shipments_for_order)
        self.delivery_by_stop = DataLoader(self._deliveries)
        self.shipment = DataLoader(self._shipment_by_id)

    async def _customers(self, keys):
        def inner():
            rows = CustomerRepository(self.tenant).by_ids(keys)
            return _map(keys, rows)

        return await sync_to_async(inner)()

    async def _warehouses(self, keys):
        def inner():
            rows = WarehouseRepository(self.tenant).by_ids(keys)
            return _map(keys, rows)

        return await sync_to_async(inner)()

    async def _addresses(self, keys):
        def inner():
            rows = AddressRepository(self.tenant).by_ids(keys)
            return _map(keys, rows)

        return await sync_to_async(inner)()

    async def _drivers(self, keys):
        def inner():
            rows = DriverRepository(self.tenant).by_ids(keys)
            return _map(keys, rows)

        return await sync_to_async(inner)()

    async def _vehicles(self, keys):
        def inner():
            rows = VehicleRepository(self.tenant).by_ids(keys).select_related("vehicle_type")
            return _map(keys, rows)

        return await sync_to_async(inner)()

    async def _items(self, keys):
        def inner():
            rows = OrderItemRepository(self.tenant).for_orders(keys)
            grouped = defaultdict(list)
            for row in rows:
                grouped[str(row.order_id)].append(row)
            return [grouped.get(str(k), []) for k in keys]

        return await sync_to_async(inner)()

    async def _stops(self, keys):
        def inner():
            rows = RouteStopRepository(self.tenant).for_routes(keys)
            grouped = defaultdict(list)
            for row in rows:
                grouped[str(row.route_id)].append(row)
            return [grouped.get(str(k), []) for k in keys]

        return await sync_to_async(inner)()

    async def _assignments(self, keys):
        def inner():
            rows = RouteAssignmentRepository(self.tenant).for_routes(keys)
            return _map(keys, rows, attr="route_id")

        return await sync_to_async(inner)()

    async def _shipments_for_order(self, keys):
        def inner():
            links = ShipmentItemRepository(self.tenant).for_orders(keys)
            grouped = defaultdict(set)
            shipment_ids = set()
            for link in links:
                grouped[str(link.order_item.order_id)].add(link.shipment_id)
                shipment_ids.add(link.shipment_id)
            ships = {
                s.id: s
                for s in ShipmentRepository(self.tenant).by_ids(shipment_ids)
            }
            return [[ships[sid] for sid in grouped.get(str(k), []) if sid in ships] for k in keys]

        return await sync_to_async(inner)()

    async def _shipment_by_id(self, keys):
        def inner():
            rows = ShipmentRepository(self.tenant).by_ids(keys)
            return _map(keys, rows)

        return await sync_to_async(inner)()

    async def _deliveries(self, keys):
        def inner():
            rows = DeliveryRepository(self.tenant).for_stops(keys)
            return _map(keys, rows, attr="route_stop_id")

        return await sync_to_async(inner)()
