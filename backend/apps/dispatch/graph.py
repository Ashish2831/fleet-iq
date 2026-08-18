from __future__ import annotations

import uuid

from apps.dispatch.services import apply_proposal, build_proposal, should_auto
from apps.orders.models import Order
from apps.tracking import redis_state as rs


def run_dispatch(tenant, order_id, *, auto: bool = True):
    """Explicit nodes: load → lock → solve → policy → apply|wait → unlock.

    This is the LangGraph-shaped workflow without an LLM in the solve node.
    """
    order = Order.objects.for_tenant(tenant).filter(id=order_id).first()
    if not order:
        return None
    token = str(uuid.uuid4())
    lock = rs.order_lock_key(tenant, order.id)
    got = rs.acquire(lock, token, ttl=30)
    try:
        proposal = build_proposal(tenant=tenant, order=order)
        if auto and should_auto(proposal, order) and proposal.status == proposal.Status.PENDING:
            return apply_proposal(proposal)
        return proposal
    finally:
        if got is True:
            rs.release(lock, token)
