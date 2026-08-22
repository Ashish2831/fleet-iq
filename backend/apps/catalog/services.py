from apps.common.errors import NotFound
from apps.common.repositories import AddressRepository, CustomerRepository, WarehouseRepository
from apps.common.sanitize import sanitize_text


def create_warehouse(*, tenant, code: str, name: str, address_id, status: str | None = None):
    address = AddressRepository(tenant).get(address_id)
    if not address:
        raise NotFound("Address not found")
    data = {
        "code": sanitize_text(code, max_len=32),
        "name": sanitize_text(name, max_len=255),
        "address": address,
    }
    if status:
        data["status"] = status
    return WarehouseRepository(tenant).create(**data)


def create_customer(*, tenant, name: str, email: str = "", phone: str = ""):
    return CustomerRepository(tenant).create(
        name=sanitize_text(name, max_len=255),
        email=sanitize_text(email, max_len=254),
        phone=sanitize_text(phone, max_len=32),
    )
