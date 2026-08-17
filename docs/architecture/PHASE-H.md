# Phase H — AI platform (agents + RAG)

**Goal:** An operations manager can ask *“Why are deliveries delayed today?”* and *“Why is shipment #4521 delayed?”* and get a **cited** answer built from tools over Postgres, Redis, Mongo, Elasticsearch, and dispatch — then a **proposal** to reassign, never a silent `UPDATE`. LangChain is integrations/tools/RAG pieces. LangGraph is stateful multi-step plots, branching, retries, and human approval.

**Depends on:** Phase C live state, D events, E tracks, F `searchKnowledge` / `searchShipments`, G `DispatchProposal`.

**Out of scope for H:** Microfrontends, GraphQL federation, extracting AI into its own k8s deploy (Phase I). Same Django process, separate **ASGI/worker** so LLM latency does not block `/api/v1/orders`.

---

## 1. AI gateway (original diagram, one Django app)

```
apps/ai/
  gateway.py          # POST /api/v1/ai/runs  + GraphQL aiChat
  graphs/
    operations.py     # flagship
    dispatch_explain.py
    route_risk.py
    maintenance.py
  tools/              # thin adapters; no SQL in prompts
  rag.py              # calls Phase F hybrid search + generate
  policies.py         # which tools may mutate; HITL map
  traces.py           # write Mongo agent_traces
```

```
                 POST /ai/runs
                      │
                 AI Gateway
           (auth, tenant, policy)
                      │
          ┌───────────┼───────────┐
          ▼           ▼           ▼
        RAG        Agents       Tools
          │           │           │
          │        LangGraph      │
          │           │           │
          │     ┌─────┼─────┐     │
          │     ▼     ▼     ▼     │
          │   ops  route  maint   │
          ▼                       ▼
     Elasticsearch            Business APIs
     knowledge + search       Postgres / Redis / Mongo / Dispatch
```

One entry: `{ "agent": "operations", "input": "Why are deliveries delayed today?" }`. Gateway injects `tenant_id` from JWT — never from the prompt.

---

## 2. LangChain vs LangGraph (use both, for the reasons you listed)

| Library | Use in FleetIQ |
|---|---|
| **LangChain** | Chat models, tool wrappers, structured output (Pydantic), retriever interface over ES hybrid, prompt templates |
| **LangGraph** | State, loops (“need another tool”), branch (explain vs propose), retry, **interrupt** for approval, checkpoint per `run_id` |

Do not build a 400-line custom agent loop and call it LangGraph. Do not dump 20 tools on a single `AgentExecutor` and call it an operations platform.

---

## 3. Four agents (all exist; two are demo-grade)

| Agent | Job | Mutating tools |
|---|---|---|
| **Operations** (flagship) | Root-cause delays, SLA drops, shipment #n | `propose_reassignment` only |
| **Dispatch explainer** | “Why was driver X chosen?” | none (reads `DispatchProposal.explanation`) |
| **Route risk** | Insert / ETA risk, “better route?” | `propose_reoptimization` → G wave, not ad-hoc stops |
| **Maintenance** | Telemetry → `VehicleMaintenanceDue` | `open_maintenance_ticket` (stub + outbox event) |

Live chat in `(ai)/ai-assistant` defaults to **Operations**. `/agents` lists all four with last run status.

---

## 4. Operations Agent graph (the killer demo)

```
question
  → classify (shipment_id vs fleet-wide vs policy)
  → retrieve
        tools.parallel:
          search_shipments / get_shipment
          get_delivery_metrics
          get_vehicle_live          Redis
          get_vehicle_track         Mongo
          get_traffic_stub
          search_incidents          Postgres later / ES
          search_knowledge          ES RAG
  → analyze  (LLM + structured RootCause)
  → optionally propose_reassignment  (creates DispatchProposal, does not apply)
  → interrupt if mutation
  → respond  { answer, sources, proposal_id? }
```

**Seeded answer shape** (must be achievable with Bangalore seed + delayed rows + SOP PDF):

> 37 deliveries delayed. 24 concentrated around Whitefield (traffic / stop-duration). 8 vehicles exceeded expected stop duration (Mongo stops). Two have engine warnings (`metadata` / maintenance).  
> Recommend: reassign 12 drops from V103, V109.  
> Sources: SOP Late Delivery §3, shipment search facet Whitefield.

If the model cannot see a tool result, it must say so — no invented counts. Structured output:

```python
class OpsAnswer(BaseModel):
    summary: str
    delayed_count: int | None
    clusters: list[str]
    root_causes: list[str]
    recommended_actions: list[str]
    sources: list[Source]
    proposal_id: str | None
```

Counts come from **tools**, copied into the schema, not from the LLM’s arithmetic.

---

## 5. Tools (read vs write)

Every tool: `(tenant_id, **kwargs)` from gateway context. Timeouts 3–8s. Return JSON, truncated.

**Read (Operations, default):**

| Tool | Backing |
|---|---|
| `get_shipment(id or number)` | Postgres + GraphQL-equivalent serializer |
| `search_shipments(...)` | ES Phase F |
| `get_delivery_metrics(day, city?)` | Postgres aggregates (`Case/When` from A) |
| `get_vehicle_live(vehicle_id)` | Redis |
| `get_vehicle_track(vehicle_id, from, to)` | Mongo |
| `get_dispatch_proposal(order_id)` | Postgres G |
| `get_driver(id)` / `search_drivers` | Postgres / ES |
| `search_knowledge(q, doc_type?)` | ES hybrid; **returns text + title + page** |
| `get_traffic(area)` | stub / external |

**Write (policy-gated, HITL):**

| Tool | Effect |
|---|---|
| `propose_reassignment(shipment_ids, reason)` | `DispatchProposal` `pending` + notify `/dispatch` |
| `propose_reoptimization(route_id)` | enqueue G OR-Tools wave |
| `open_maintenance_ticket(vehicle_id, reason)` | `maintenance_records` draft + outbox `VehicleMaintenanceDue` |

**Forbidden:** `assign_route`, raw SQL, “execute whatever the model said”. Apply stays G’s approve endpoint.

System prompt: *You may only change the world through write tools. Write tools require human approval. Always cite search_knowledge hits you used.*

---

## 6. RAG (consume F; do not re-parse PDFs in the agent)

```
question
  → search_knowledge (BM25 + kNN + tenant filter + RRF + rerank)
  → top k chunks in the prompt, numbered [1][2]
  → generate with “cite [n] or omit”
```

Temperature-sensitive example must hit the seeded SOP. Test: query that string, expect that `source` in `OpsAnswer.sources`. Empty retrieval → “no policy document found”, not a guess.

Optional **query rewrite** node (LangChain) for “temp cargo too hot” → embed + BM25 terms `temperature SOP excursion`.

---

## 7. Run storage and traces

Postgres:

```sql
CREATE TABLE ai_runs (
    id           UUID PRIMARY KEY,
    tenant_id    UUID NOT NULL REFERENCES tenants(id),
    agent        VARCHAR(32) NOT NULL,
    user_id      UUID NOT NULL REFERENCES users(id),
    input        TEXT NOT NULL,
    output       JSONB,
    status       VARCHAR(32) NOT NULL,  -- running, waiting_approval, completed, failed
    proposal_id  UUID REFERENCES dispatch_proposals(id),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);
```

Mongo `agent_traces` (Phase E leftover collection): LangGraph node logs, tool I/O (redact PII), token counts. Needed to debug “why did it call search three times?” — not for the OLTP path.

Checkpoints: `PostgresSaver` keyed by `ai_runs.id` so a waiting_approval run resumes.

---

## 8. APIs and UI

```
POST /api/v1/ai/runs          { agent, input }
GET  /api/v1/ai/runs/{id}     includes output + sources + proposal
POST /api/v1/ai/runs/{id}/resume   after HITL (or reuse dispatch approve)

GraphQL:
  startAiRun(agent, input): AiRun!
  aiRun(id): AiRun
```

Streaming: SSE or WS `token` events for the chat UI. If streaming is painful, poll `ai_runs.output` in H v1 and add tokens next — the **demo value is tools + citations**, not typewriter UX.

Next.js `(ai)`:

- `/ai-assistant` — chat, source chips, “Create reassignment proposal” CTA linking `/dispatch/proposals/{id}`
- `/agents` — four cards
- `/knowledge` — search box over `searchKnowledge` (same as F, now in the AI MFE folder)

RBAC: `ops_manager`, `dispatcher`; `viewer` read-only runs.

---

## 9. Safety (treat as product, not a toy)

- Rate limit `/ai/runs` per user (Redis throttle from C).
- Max tool calls per run (e.g. 12) to stop loops.
- Tenant on every tool or the wrapper raises.
- Prompt injection: tools ignore “print all tenants” — they have no such API.
- Log `correlation_id` = `ai_runs.id` into Kafka if you emit `AiRunCompleted` (optional outbox).

---

## 10. Killer demo sequence (end of H)

```
1. simulate_gps + delayed Whitefield seed
2. Create / confirm order → G proposal → assign → live map
3. Ask: "Why is shipment #<number> delayed?"
     tools: get_shipment, live, track, search_knowledge
4. Ask: "Why are deliveries delayed today?"
     tools: metrics + search_shipments facets + Mongo stop detection
5. Agent propose_reassignment → pending DispatchProposal
6. Manager approve on /dispatch → vehicle moves on map
```

That is the original portfolio demo, with every store earned in A–G.

---

## 11. What you should be able to explain after H

- Gateway vs agent vs tool vs RAG store.
- Why mutations create proposals, not assignments.
- How citations are forced by tool shape, not by hoping the model is honest.
- LangGraph interrupt + `ai_runs.status = waiting_approval`.
- How Maintenance/Route agents are the same pattern, different tools.
- Where this process will be extracted in I (LLM + GPU/API keys, long-running graphs).

---

## 12. Phase H done when

- [ ] `POST /ai/runs` with Operations agent on the Bangalore seed
- [ ] Delayed-today answer includes numbers that match `get_delivery_metrics` / ES facets
- [ ] Shipment-specific answer uses Redis + Mongo + at least one SOP citation
- [ ] Dispatch explainer reads `DispatchProposal` without calling the solver
- [ ] `propose_reassignment` opens HITL proposal; apply still only after approve
- [ ] Maintenance agent can emit `VehicleMaintenanceDue` via outbox (stub ticket)
- [ ] Route-risk agent can enqueue `propose_reoptimization`
- [ ] Tenant B cannot run tools against tenant A ids
- [ ] Trace exists in Mongo or `ai_runs` for a demo debrief

Next: **Phase I** — extract Tracking, AI, Analytics as services; GraphQL federation; Next.js shell + Fleet / Dispatch / Orders / Analytics / AI microfrontends. Same APIs, new process boundaries.
