from apps.common.repositories import DriverRepository, VehicleRepository
from apps.common.sanitize import sanitize_text


def create_driver(*, tenant, **data):
    if "full_name" in data:
        data["full_name"] = sanitize_text(str(data["full_name"]), max_len=255)
    if "employee_code" in data:
        data["employee_code"] = sanitize_text(str(data["employee_code"]), max_len=64)
    if "phone" in data and data["phone"]:
        data["phone"] = sanitize_text(str(data["phone"]), max_len=32)
    return DriverRepository(tenant).create(**data)


def create_vehicle(*, tenant, **data):
    if "plate_number" in data:
        data["plate_number"] = sanitize_text(str(data["plate_number"]), max_len=32)
    if "make" in data and data["make"]:
        data["make"] = sanitize_text(str(data["make"]), max_len=64)
    if "model" in data and data["model"]:
        data["model"] = sanitize_text(str(data["model"]), max_len=64)
    return VehicleRepository(tenant).create(**data)
