import logging

from django.apps import AppConfig

logger = logging.getLogger("apps.common.events")


class CommonConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.common"
    label = "common"

    def ready(self):
        from apps.common.patterns.observer import domain_events

        def _log_domain_event(event):
            logger.info(
                "domain.event",
                extra={
                    "event_type": event.type,
                    "tenant_id": event.tenant_id,
                    "aggregate_id": event.aggregate_id,
                },
            )

        # Idempotent registration across autoreload
        if not getattr(domain_events, "_fleetiq_logging_bound", False):
            domain_events.on("*", _log_domain_event)
            domain_events._fleetiq_logging_bound = True  # type: ignore[attr-defined]
