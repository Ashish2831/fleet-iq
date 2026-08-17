# FleetIQ Architecture

FleetIQ is a multi-tenant logistics and fleet intelligence platform. The **target architecture keeps every technology** in the original design (Postgres, Django, Next.js, GraphQL, microfrontends, Kafka, outbox, Redis, MongoDB, Elasticsearch, WebSockets, LangChain, LangGraph, RAG). Technologies are **sequenced**, not dropped.

| Doc | Purpose |
|---|---|
| [ROADMAP.md](./ROADMAP.md) | Phases A–I. Where each tech is introduced and why. |
| [DOMAIN.md](./DOMAIN.md) | Canonical domain model and cardinalities. |
| [PHASE-A.md](./PHASE-A.md) | Foundation: Postgres schema, Django apps, ORM practice map. |
| [PHASE-B.md](./PHASE-B.md) | REST + GraphQL BFF on one Django process, Next.js route groups. |
| [PHASE-C.md](./PHASE-C.md) | GPS ingest, Redis live state, Django Channels, live map. |
| [PHASE-D.md](./PHASE-D.md) | Transactional outbox, Kafka/Redpanda, idempotent consumers, DLQ. |
| [PHASE-E.md](./PHASE-E.md) | MongoDB GPS history from Kafka; TTL, indexes, downsample. |
| [PHASE-F.md](./PHASE-F.md) | Elasticsearch ops search + hybrid BM25/vector RAG index. |
| [PHASE-G.md](./PHASE-G.md) | Deterministic dispatch + LangGraph approval workflow. |
| [PHASE-H.md](./PHASE-H.md) | AI gateway, four agents, RAG tools, HITL mutations. |
| [PHASE-I.md](./PHASE-I.md) | Extract Tracking/AI/Analytics, GraphQL federation, MFEs. |

**Implement in order: A → I.** Start coding at A (models, tenants, Bangalore seed). I is empty Docker boxes if A–H are not running.
