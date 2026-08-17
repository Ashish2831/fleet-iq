from collections import defaultdict

from asgiref.sync import sync_to_async
from strawberry.dataloader import DataLoader

from apps.catalog.models import Address, Customer, Warehouse
from apps.fleet.models import Driver, Vehicle
from apps.orders.models import OrderItem
from apps.routing.models import RouteAssignment, RouteStop
from apps.shipments.models import Delivery, Shipment, ShipmentItem


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
            rows = Customer.objects.for_tenant(self.tenant).filter(id__in=keys)
            return _map(keys, rows)

        return await sync_to_async(inner)()

    async def _warehouses(self, keys):
        def inner():
            rows = Warehouse.objects.for_tenant(self.tenant).filter(id__in=keys)
            return _map(keys, rows)

        return await sync_to_async(inner)()

    async def _addresses(self, keys):
        def inner():
            rows = Address.objects.for_tenant(self.tenant).filter(id__in=keys)
            return _map(keys, rows)

        return await sync_to_async(inner)()

    async def _drivers(self, keys):
        def inner():
            rows = Driver.objects.for_tenant(self.tenant).filter(id__in=keys)
            return _map(keys, rows)

        return await sync_to_async(inner)()

    async def _vehicles(self, keys):
        def inner():
            rows = Vehicle.objects.select_related("vehicle_type").for_tenant(self.tenant).filter(id__in=keys)
            return _map(keys, rows)

        return await sync_to_async(inner)()

    async def _items(self, keys):
        def inner():
            rows = OrderItem.objects.for_tenant(self.tenant).filter(order_id__in=keys)
            grouped = defaultdict(list)
            for row in rows:
                grouped[str(row.order_id)].append(row)
            return [grouped.get(str(k), []) for k in keys]

        return await sync_to_async(inner)()

    async def _stops(self, keys):
        def inner():
            rows = (
                RouteStop.objects.for_tenant(self.tenant)
                .filter(route_id__in=keys)
                .order_by("sequence")
            )
            grouped = defaultdict(list)
            for row in rows:
                grouped[str(row.route_id)].append(row)
            return [grouped.get(str(k), []) for k in keys]

        return await sync_to_async(inner)()

    async def _assignments(self, keys):
        def inner():
            rows = (
                RouteAssignment.objects.select_related("driver", "vehicle")
                .for_tenant(self.tenant)
                .filter(route_id__in=keys)
            )
            return _map(keys, rows, attr="route_id")

        return await sync_to_async(inner)()

    async def _shipments_for_order(self, keys):
        def inner():
            links = (
                ShipmentItem.objects.select_related("order_item")
                .for_tenant(self.tenant)
                .filter(order_item__order_id__in=keys)
            )
            grouped = defaultdict(set)
            shipment_ids = set()
            for link in links:
                grouped[str(link.order_item.order_id)].add(link.shipment_id)
                shipment_ids.add(link.shipment_id)
            ships = {s.id: s for s in Shipment.objects.for_tenant(self.tenant).filter(id__in=shipment_ids)}
            return [[ships[sid] for sid in grouped.get(str(k), []) if sid in ships] for k in keys]

        return await sync_to_async(inner)()

    async def _shipment_by_id(self, keys):
        def inner():
            rows = Shipment.objects.for_tenant(self.tenant).filter(id__in=keys)
            return _map(keys, rows)

        return await sync_to_async(inner)()

    async def _deliveries(self, keys):
        def inner():
            rows = Delivery.objects.for_tenant(self.tenant).filter(route_stop_id__in=keys)
            return _map(keys, rows, attr="route_stop_id")

        return await sync_to_async(inner)()
