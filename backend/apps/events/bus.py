from __future__ import annotations

import json
import logging
import threading
from collections import defaultdict
from dataclasses import dataclass, field

from django.conf import settings

from apps.events.envelopes import kafka_headers

logger = logging.getLogger(__name__)


@dataclass
class BusRecord:
    topic: str
    key: str
    value: dict
    headers: dict = field(default_factory=dict)
    offset: int = 0


class EventBus:
    def produce(self, topic: str, key: str, value: dict, headers: dict | None = None) -> None:
        raise NotImplementedError

    def poll(self, group: str, topics: list[str], max_records: int = 50) -> list[BusRecord]:
        raise NotImplementedError

    def reset_group(self, group: str) -> None:
        return None

    def ensure_topics(self, topics: list[str] | tuple[str, ...]) -> None:
        return None

    def records(self, topic: str) -> list[BusRecord]:
        return []


class InMemoryBus(EventBus):
    """Process-local broker so tests do not need Redpanda."""

    def __init__(self):
        self.topics: dict[str, list[BusRecord]] = defaultdict(list)
        self._cursors: dict[tuple[str, str], int] = {}
        self._lock = threading.Lock()

    def produce(self, topic: str, key: str, value: dict, headers: dict | None = None) -> None:
        with self._lock:
            rec = BusRecord(
                topic=topic,
                key=str(key),
                value=value,
                headers=headers or {},
                offset=len(self.topics[topic]),
            )
            self.topics[topic].append(rec)

    def poll(self, group: str, topics: list[str], max_records: int = 50) -> list[BusRecord]:
        out: list[BusRecord] = []
        with self._lock:
            for topic in topics:
                cur = self._cursors.get((group, topic), 0)
                batch = self.topics[topic][cur : cur + max_records]
                self._cursors[(group, topic)] = cur + len(batch)
                out.extend(batch)
        return out

    def reset_group(self, group: str) -> None:
        with self._lock:
            for key in list(self._cursors):
                if key[0] == group:
                    self._cursors[key] = 0

    def clear(self) -> None:
        with self._lock:
            self.topics.clear()
            self._cursors.clear()

    def ensure_topics(self, topics: list[str] | tuple[str, ...]) -> None:
        with self._lock:
            for topic in topics:
                self.topics.setdefault(topic, [])

    def records(self, topic: str) -> list[BusRecord]:
        with self._lock:
            return list(self.topics.get(topic, []))


class KafkaBus(EventBus):
    def __init__(self, bootstrap: str):
        from kafka import KafkaProducer

        self.bootstrap = bootstrap
        self._producer = KafkaProducer(
            bootstrap_servers=bootstrap.split(","),
            acks="all",
            linger_ms=50,
            retries=3,
            key_serializer=lambda k: k.encode() if isinstance(k, str) else k,
            value_serializer=lambda v: json.dumps(v).encode(),
            client_id=getattr(settings, "KAFKA_CLIENT_ID", "fleetiq"),
        )
        self._consumers: dict[str, object] = {}

    def produce(self, topic: str, key: str, value: dict, headers: dict | None = None) -> None:
        hdrs = [(k, v if isinstance(v, bytes) else str(v).encode()) for k, v in (headers or {}).items()]
        if not hdrs:
            hdrs = kafka_headers(value)
        future = self._producer.send(topic, key=str(key), value=value, headers=hdrs)
        future.get(timeout=10)

    def ensure_topics(self, topics: list[str] | tuple[str, ...]) -> None:
        from kafka.admin import KafkaAdminClient, NewTopic
        from kafka.errors import TopicAlreadyExistsError

        admin = KafkaAdminClient(bootstrap_servers=self.bootstrap.split(","), client_id="fleetiq-admin")
        try:
            admin.create_topics(
                [NewTopic(name=t, num_partitions=6, replication_factor=1) for t in topics]
            )
        except TopicAlreadyExistsError:
            pass
        finally:
            admin.close()

    def poll(self, group: str, topics: list[str], max_records: int = 50) -> list[BusRecord]:
        from kafka import KafkaConsumer, TopicPartition

        consumer = self._consumers.get(group)
        if consumer is None:
            consumer = KafkaConsumer(
                *topics,
                bootstrap_servers=self.bootstrap.split(","),
                group_id=group,
                enable_auto_commit=False,
                auto_offset_reset="earliest",
                consumer_timeout_ms=500,
                value_deserializer=lambda b: json.loads(b.decode()) if b else {},
                key_deserializer=lambda b: b.decode() if b else "",
            )
            self._consumers[group] = consumer
        out = []
        for msg in consumer:
            headers = {k: (v.decode() if isinstance(v, bytes) else v) for k, v in (msg.headers or [])}
            out.append(
                BusRecord(
                    topic=msg.topic,
                    key=msg.key or "",
                    value=msg.value if isinstance(msg.value, dict) else {},
                    headers=headers,
                    offset=msg.offset,
                )
            )
            consumer.commit({TopicPartition(msg.topic, msg.partition): msg.offset + 1})
            if len(out) >= max_records:
                break
        return out


_bus: EventBus | None = None


def get_bus() -> EventBus:
    global _bus
    if _bus is None:
        if getattr(settings, "KAFKA_ENABLED", False):
            _bus = KafkaBus(settings.KAFKA_BOOTSTRAP_SERVERS)
        else:
            _bus = InMemoryBus()
    return _bus


def set_bus(bus: EventBus | None) -> None:
    global _bus
    _bus = bus


def reset_bus() -> InMemoryBus:
    bus = InMemoryBus()
    set_bus(bus)
    return bus
