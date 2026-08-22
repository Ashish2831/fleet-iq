from apps.common.repositories import UserRepository
from apps.common.sanitize import sanitize_text


def update_profile(*, user, full_name: str):
    name = sanitize_text(full_name, max_len=120)
    return UserRepository(user.tenant).update(user, full_name=name)
