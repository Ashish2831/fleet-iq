ORDERS = "fleetiq.orders"
ROUTING = "fleetiq.routing"
DELIVERIES = "fleetiq.deliveries"
FLEET = "fleetiq.fleet"
PAYMENTS = "fleetiq.payments"
LOCATION = "fleetiq.vehicle.location"
DLQ = "fleetiq.dlq"

TOPIC_BY_EVENT = {
    "OrderCreated": ORDERS,
    "OrderConfirmed": ORDERS,
    "OrderAssigned": ORDERS,
    "OrderCancelled": ORDERS,
    "RouteCreated": ROUTING,
    "RouteUpdated": ROUTING,
    "DriverAssigned": ROUTING,
    "DriverAssigned": ROUTING,
    "DeliveryStarted": DELIVERIES,
    "DeliveryCompleted": DELIVERIES,
    "DeliveryFailed": DELIVERIES,
    "VehicleOffline": FLEET,
    "VehicleMaintenanceDue": FLEET,
    "PaymentCompleted": PAYMENTS,
    "VehicleLocationUpdated": LOCATION,
    "VehicleLocationUpdated": LOCATION,
}

ALL_DOMAIN = (ORDERS, ROUTING, DELIVERIES, FLEET, PAYMENTS)
ALL_TOPICS = ALL_DOMAIN + (LOCATION, DLQ)
