from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.catalog.models import CustomerAddress
from apps.common.repositories import (
    AddressRepository,
    CustomerRepository,
    DriverRepository,
    VehicleRepository,
    WarehouseRepository,
)
from apps.fleet.models import (
    Driver,
    FuelTransaction,
    MaintenanceRecord,
    Vehicle,
    VehicleAssignment,
    VehicleType,
)
from apps.identity.models import Permission, Role, Tenant, User, UserRole
from apps.orders.models import Order
from apps.orders.services import create_order
from apps.routing.models import Route
from apps.routing.services import create_route_with_stops
from apps.shipments.models import Delivery
from apps.shipments.services import create_shipment

SLUG = "acme-logistics"

PLACES = [
    ("Peenya Warehouse Rd", "Bengaluru", 13.0329, 77.5273, "warehouse"),
    ("ITPL Main Rd, Whitefield", "Bengaluru", 12.9698, 77.7499, "warehouse"),
    ("100 Feet Rd, Indiranagar", "Bengaluru", 12.9784, 77.6408, "customer"),
    ("5th Block, Koramangala", "Bengaluru", 12.9352, 77.6245, "customer"),
    ("HSR Layout 27th Main", "Bengaluru", 12.9121, 77.6446, "customer"),
    ("Jayanagar 4th T Block", "Bengaluru", 12.9308, 77.5838, "customer"),
    ("Hebbal Outer Ring Rd", "Bengaluru", 13.0358, 77.5970, "customer"),
    ("Electronic City Phase 1", "Bengaluru", 12.8458, 77.6652, "customer"),
    ("Whitefield Graphite India", "Bengaluru", 12.9732, 77.7110, "customer"),
    ("MG Road Brigade", "Bengaluru", 12.9758, 77.6055, "customer"),
]

CUSTOMER_NAMES = [
    "Nimbus Retail",
    "Deccan Pharma",
    "Orion Fresh",
    "Kaveri Mart",
    "Silicon Components",
    "Garden City Foods",
    "Whitefield BioLabs",
    "Koramangala Kitchen",
]

DRIVER_NAMES = [
    "Arjun Rao",
    "Meera Iyer",
    "Vikram Singh",
    "Divya Nair",
    "Ramesh Kulkarni",
    "Sana Sheikh",
    "Harish Gowda",
    "Priya Menon",
    "Imran Khan",
    "Lakshmi Prasad",
    "Nikhil Joshi",
    "Ananya Das",
]


class Command(BaseCommand):
    help = "Load Bangalore demo tenant acme-logistics (and a tiny isolation tenant)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing acme-logistics / beta-freight tenants first.",
        )

    def handle(self, *args, **options):
        if options["reset"]:
            Tenant.objects.filter(slug__in=[SLUG, "beta-freight"]).delete()
        if Tenant.objects.filter(slug=SLUG).exists():
            self.stdout.write("Seed already present. Re-run with --reset.")
            return
        self._seed_acme()
        self._seed_beta()
        self.stdout.write(self.style.SUCCESS("Seeded acme-logistics and beta-freight."))

    def _seed_beta(self):
        tenant = Tenant.objects.create(name="Beta Freight", slug="beta-freight", status="active")
        AddressRepository(tenant).create(
            line1="Secret other-tenant road",
            city="Mumbai",
            lat=19.07,
            lng=72.87,
        )

    def _seed_acme(self):
        now = timezone.now()
        today = timezone.localdate()
        tenant = Tenant.objects.create(name="Acme Logistics", slug=SLUG, status="active")
        addresses_repo = AddressRepository(tenant)
        warehouses_repo = WarehouseRepository(tenant)
        customers_repo = CustomerRepository(tenant)
        vehicles_repo = VehicleRepository(tenant)
        drivers_repo = DriverRepository(tenant)

        perm_codes = [
            "orders.order.create",
            "orders.order.read",
            "fleet.vehicle.read",
            "fleet.vehicle.assign",
            "dispatch.route.assign",
            "ai.run.create",
        ]
        perms = {c: Permission.objects.get_or_create(codename=c, defaults={"description": c})[0] for c in perm_codes}

        roles = {}
        for name in ("owner", "ops_manager", "dispatcher", "driver", "viewer"):
            role = Role.objects.create(tenant=tenant, name=name)
            role.permissions.add(*perms.values())
            roles[name] = role

        owner = User.objects.create(
            tenant=tenant,
            email="ops@acme-logistics.example",
            full_name="Acme Ops",
            hashed_password=make_password("password"),
        )
        UserRole.objects.create(user=owner, role=roles["ops_manager"])

        addresses = [
            addresses_repo.create(
                line1=line1,
                city=city,
                state="Karnataka",
                postal_code="560001",
                lat=lat,
                lng=lng,
            )
            for line1, city, lat, lng, _kind in PLACES
        ]
        peenya = warehouses_repo.create(
            code="PNY", name="Peenya DC", address=addresses[0]
        )
        whitefield_wh = warehouses_repo.create(
            code="WFD", name="Whitefield Depot", address=addresses[1]
        )

        customers = []
        for i, name in enumerate(CUSTOMER_NAMES):
            addr = addresses[2 + i]
            customer = customers_repo.create(
                name=name,
                email=f"ops{i}@customer.example",
                phone=f"+91980000000{i}",
            )
            CustomerAddress.objects.create(
                tenant=tenant,
                customer=customer,
                address=addr,
                label="delivery",
                is_default=True,
            )
            customers.append((customer, addr))

        van = VehicleType.objects.create(
            tenant=tenant, name="van", max_weight_kg=Decimal("1200"), requires_skills=[]
        )
        reefer = VehicleType.objects.create(
            tenant=tenant,
            name="reefer",
            max_weight_kg=Decimal("800"),
            requires_skills=["reefer"],
        )
        bike = VehicleType.objects.create(
            tenant=tenant, name="bike", max_weight_kg=Decimal("30"), requires_skills=[]
        )

        types_cycle = [van, van, van, van, van, reefer, reefer, reefer, bike, bike]
        vehicles = []
        for i, vtype in enumerate(types_cycle):
            vehicles.append(
                vehicles_repo.create(
                    vehicle_type=vtype,
                    plate_number=f"KA01AB{1000 + i}",
                    make="Tata" if vtype.name != "bike" else "Bajaj",
                    model="Ace" if vtype.name == "van" else vtype.name,
                    status=Vehicle.Status.ACTIVE,
                    current_odometer_km=Decimal(str(12000 + i * 400)),
                    metadata={"device_id": f"IMEI-ACM-{i:04d}"},
                )
            )

        drivers = []
        for i, full_name in enumerate(DRIVER_NAMES):
            skills = ["reefer"] if i in (5, 6, 7) else []
            if i == 2:
                skills = ["heavy"]
            drivers.append(
                drivers_repo.create(
                    employee_code=f"DRV-{i + 1:03d}",
                    full_name=full_name,
                    phone=f"+9198111000{i:02d}",
                    skills=skills,
                    status=Driver.Status.AVAILABLE,
                    home_lat=12.97 + i * 0.004,
                    home_lng=77.59 + i * 0.006,
                    rating=Decimal("4.20") + Decimal("0.05") * (i % 5),
                )
            )

        for i in range(10):
            VehicleAssignment.objects.create(
                tenant=tenant,
                driver=drivers[i],
                vehicle=vehicles[i],
                starts_at=now - timedelta(days=3),
            )

        for v in vehicles[:3]:
            for n in range(4):
                MaintenanceRecord.objects.create(
                    tenant=tenant,
                    vehicle=v,
                    kind="service" if n % 2 == 0 else "inspection",
                    occurred_at=now - timedelta(days=30 * (n + 1)),
                    odometer_km=Decimal(str(8000 + n * 1000)),
                    cost=Decimal("2500.00"),
                )
            FuelTransaction.objects.create(
                tenant=tenant,
                vehicle=v,
                driver=drivers[0],
                occurred_at=now - timedelta(days=2),
                liters=Decimal("40.00"),
                cost=Decimal("3800.00"),
            )

        warehouses = [peenya, whitefield_wh]
        orders = []
        for i in range(20):
            customer, addr = customers[i % 8]
            warehouse = warehouses[i % 2]
            items = [
                {
                    "sku": f"SKU-{i + 1:03d}A",
                    "description": "Carton",
                    "quantity": Decimal("2"),
                    "weight_kg": Decimal("10") if i % 7 != 0 else Decimal("80"),
                    "temperature_min": Decimal("2") if i % 5 == 0 else None,
                    "temperature_max": Decimal("8") if i % 5 == 0 else None,
                }
            ]
            if i % 4 == 0:
                items.append(
                    {
                        "sku": f"SKU-{i + 1:03d}B",
                        "description": "Split line",
                        "quantity": Decimal("1"),
                        "weight_kg": Decimal("15"),
                    }
                )
            order = create_order(
                tenant=tenant,
                customer=customer,
                warehouse=warehouse,
                order_number=f"ACM-{1001 + i}",
                items=items,
                deadline_at=now + timedelta(hours=8),
                status=Order.Status.CONFIRMED,
            )
            orders.append((order, customer, addr, warehouse))

        shipments = []
        for i, (order, customer, addr, warehouse) in enumerate(orders):
            ois = list(order.items.all())
            promised = now + timedelta(hours=6)
            if i < 5:
                promised = now - timedelta(hours=3)
            status = Delivery.Status.PENDING
            ship_status = "planned"
            if i < 5:
                ship_status = "in_transit"
            first = create_shipment(
                tenant=tenant,
                warehouse=warehouse,
                delivery_address=addr,
                shipment_number=f"SHP-{2001 + i}",
                order_item_quantities=[(ois[0], ois[0].quantity)],
                promised_at=promised,
                status=ship_status,
            )
            shipments.append((first, warehouse, addr, promised, ship_status))
            if len(ois) > 1:
                extra = create_shipment(
                    tenant=tenant,
                    warehouse=warehouse,
                    delivery_address=addr,
                    shipment_number=f"SHP-{2001 + i}B",
                    order_item_quantities=[(ois[1], ois[1].quantity)],
                    promised_at=promised,
                )
                shipments.append((extra, warehouse, addr, promised, "planned"))

        def route_stops(wh, ship_slice, delayed=False):
            specs = [
                {
                    "stop_type": "depot",
                    "sequence": 1,
                    "address": wh.address,
                    "warehouse": wh,
                }
            ]
            seq = 2
            for ship, _, addr, _promised, ship_status in ship_slice:
                specs.append(
                    {
                        "stop_type": "pickup",
                        "sequence": seq,
                        "address": wh.address,
                        "shipment": ship,
                    }
                )
                seq += 1
                drop = {
                    "stop_type": "dropoff",
                    "sequence": seq,
                    "address": addr,
                    "shipment": ship,
                    "planned_arrival": now + timedelta(hours=seq),
                }
                if delayed and ship_status == "in_transit":
                    drop["delivery_status"] = Delivery.Status.IN_TRANSIT
                    drop["status"] = "arrived"
                seq += 1
                specs.append(drop)
            return specs

        create_route_with_stops(
            tenant=tenant,
            route_number="RT-101",
            planned_date=today,
            driver=drivers[0],
            vehicle=vehicles[0],
            status=Route.Status.IN_PROGRESS,
            stops=route_stops(peenya, shipments[0:3], delayed=True),
        )
        create_route_with_stops(
            tenant=tenant,
            route_number="RT-102",
            planned_date=today,
            driver=drivers[1],
            vehicle=vehicles[1],
            status=Route.Status.IN_PROGRESS,
            stops=route_stops(peenya, shipments[3:6], delayed=True),
        )
        create_route_with_stops(
            tenant=tenant,
            route_number="RT-103",
            planned_date=today,
            driver=drivers[5],
            vehicle=vehicles[5],
            stops=route_stops(whitefield_wh, shipments[6:9]),
        )
        create_route_with_stops(
            tenant=tenant,
            route_number="RT-104",
            planned_date=today,
            driver=drivers[8],
            vehicle=vehicles[8],
            stops=route_stops(whitefield_wh, shipments[9:12]),
        )
