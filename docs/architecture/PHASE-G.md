# Phase G — Dispatch engine

**Goal:** When an order is confirmed, a **deterministic** engine proposes driver + vehicle + (optional) route insertion. Elasticsearch supplies **candidates**. Redis supplies **live location and locks**. Postgres supplies **capacity, skills, assignments**. LangGraph runs the **workflow** (branch, retry, human approval) — it does not compute distances, capacity, or VRP.

**Depends on:** Phase B `assign_route` service, Phase C Redis locks + live hashes, Phase D `OrderCreated` / `fleetiq-dispatch` group, Phase F `searchDrivers`.

**Out of scope for G:** Operations Agent Q&A (Phase H), traffic vendor as a hard dependency (stub is enough), full city-scale VRP.

This is the original “AI Dispatch Agent” **done correctly**: the agent graph orchestrates **tools**; the tools are real code.

---

## 1. Split of responsibility (interview this first)

```
OrderConfirmed / OrderCreated
        │
        ▼
 LangGraph  (Dispatch workflow)
        │
        ├── get_available_drivers()      ES + Postgres
        ├── get_available_vehicles()     Postgres
        ├── get_vehicle_capacity()
        ├── get_current_location()       Redis
        ├── get_active_routes()          Postgres
        ├── calculate_route()            OSRM / OR-Tools
        ├── get_traffic()                stub or Maps API
        ├── calculate_eta()              Redis cache + remaining stops
        ├── calculate_delivery_cost()    simple rate card
        └── score_and_solve()            Python / OR-Tools   ← NOT the LLM
                │
                ▼
         DispatchProposal  (Postgres)
                │
         needs_approval?
            /         \
          YES          NO
           │            │
     HITL interrupt   assign_route()
           │            │
           └────┬───────┘
                ▼
         Outbox: DriverAssigned, OrderAssigned, RouteUpdated
```

The LLM (if used at all in G) may **summarize** why option 1 beat option 2 for the manager UI. It must not pick a 500 kg order onto a bike because the prompt was vague.

Tenant policy: `auto_assign_if_score_gap >= X` and `priority < P`; otherwise human approval. Same graph, different branch.

---

## 2. Django app

```
apps/dispatch/
  models.py           # DispatchProposal, DispatchCandidate (json or rows)
  constraints.py      # hard checks
  scoring.py          # weighted cost
  solver.py           # greedy + optional OR-Tools
  tools.py            # functions LangGraph binds
  graph.py            # LangGraph state machine
  consumers.py        # fleetiq-dispatch
  services.py         # propose(), approve(), reject(), apply()
```

`apps/routing/services.assign_route` stays the **only** writer of `route_assignments`. Dispatch never updates those tables except by calling that service inside a transaction + outbox.

---

## 3. Postgres: proposals (source of truth for “what the engine decided”)

```sql
CREATE TABLE dispatch_proposals (
    id              UUID PRIMARY KEY,
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    order_id        UUID NOT NULL REFERENCES orders(id),
    status          VARCHAR(32) NOT NULL DEFAULT 'pending'
                    CHECK (status IN (
                        'pending', 'approved', 'rejected',
                        'applied', 'failed', 'superseded'
                    )),
    chosen          JSONB NOT NULL,          -- driver_id, vehicle_id, route_id, stop inserts
    alternatives    JSONB NOT NULL DEFAULT '[]',
    hard_pass       BOOLEAN NOT NULL,
    score           NUMERIC(12,4),
    explanation     JSONB NOT NULL DEFAULT '{}',  -- feature breakdown, not LLM prose required
    policy          JSONB NOT NULL DEFAULT '{}',  -- auto vs hitl, weights used
    graph_run_id    VARCHAR(64),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at      TIMESTAMPTZ,
    decided_by_id   UUID REFERENCES users(id)
);
CREATE INDEX idx_dispatch_order ON dispatch_proposals(tenant_id, order_id, created_at DESC);
```

Idempotency: one **pending** proposal per order (`UNIQUE` partial index `WHERE status = 'pending'`). Replayed `OrderCreated` loads the existing pending row.

---

## 4. Hard constraints vs soft score

**Hard (reject candidate if any fail):**

| Constraint | Source |
|---|---|
| Same tenant | JWT / event |
| Driver `available` or already on a route that **can insert** this stop | Postgres |
| Current `vehicle_assignment` exists (driver has a vehicle) **or** pair driver+vehicle both free | `vehicle_assignments` |
| Vehicle `status` in `active` / `in_use`, not `maintenance` / `retired` | Postgres |
| `vehicle_type.max_weight_kg` ≥ shipment weight | Postgres |
| Skills: reefer / hazmat ⊂ `driver.skills` | Postgres array |
| Deadline feasible: `now + eta ≤ deadline_at` with slack | Redis loc + `calculate_eta` |
| Vehicle type matches (bike ≠ 500 kg) | obvious |
| Lock: `lock:order:{tid}:{order_id}` held by this worker | Redis |

**Soft (ranked, never violate hard):**

```
score =  w_dist   * distance_km          # lower better → use negative or cost
       + w_eta    * slack_minutes_inverse
       + w_util   * leftover_capacity    # fill trucks, don’t starve
       + w_fuel   * estimated_fuel_cost
       + w_priority * lateness_risk
       - w_rating * driver.rating
```

Start with explicit weights in config (`dispatch.weights`). Log them in `proposal.policy` so you can explain a decision months later.

---

## 5. Two solver modes (implement both; use greedy in the demo)

### A. Single insertion (Phase G default)

One new shipment: pick best (driver, vehicle, existing route **or** new route).

1. Candidates: ES `searchDrivers` (available + skills + geo 15 km) cap 20.
2. For each: `get_current_location` Redis; skip if no ping and policy requires live GPS.
3. Filter hard constraints in Python.
4. For remaining: cheapest insertion index on their active route (or depot start).
5. `score_and_solve` returns top 3 in `alternatives`, winner in `chosen`.

This is enough for the killer demo. It teaches candidate gen + scoring + locks.

### B. OR-Tools VRP (batch / end of wave)

Input: N unassigned shipments, M vehicles with capacities and time windows.

```
ortools.constraint_solver
  - capacity dimension (weight)
  - time dimension (deadline)
  - start at warehouse
  - optional drop penalty
```

Run **out of band** (management command `optimize_wave --date`) so a 30s solve cannot block Kafka. Store `DispatchProposal` per order or one `Route` plan per vehicle.

The LLM never calls OR-Tools by inventing matrix numbers. `calculate_route` / `score_and_solve` do.

OSRM or a static distance matrix (haversine × 1.4) is fine locally. Traffic API is `get_traffic()` stub returning `1.0` or a peak-hour multiplier.

---

## 6. Tools (bind these to LangGraph; they are also unit-testable without an LLM)

| Tool | Reads |
|---|---|
| `get_available_drivers(tenant, near, skills, limit)` | ES + Postgres |
| `get_available_vehicles(tenant, type, min_weight)` | Postgres |
| `get_vehicle_capacity(vehicle_id)` | Postgres `vehicle_types` + remaining on route |
| `get_current_location(vehicle_id)` | Redis `vehicle:{tid}:{id}` |
| `get_active_routes(driver_id)` | Postgres |
| `calculate_route(stops)` | OSRM / haversine |
| `get_traffic(corridor, when)` | stub |
| `calculate_eta(vehicle_id, destination)` | Redis ETA cache |
| `calculate_delivery_cost(...)` | naive ₹/km + weight |
| `propose_assignment(order_id)` | `scoring.py` / `solver.py` |
| `assign_driver(proposal_id)` | `assign_route` + outbox |

LangGraph node `solve` **must** call `propose_assignment` (code). Nodes `explain` may call an LLM with the JSON `explanation` to produce three sentences for the UI.

---

## 7. LangGraph workflow (what G uses LangGraph *for*)

State:

```python
class DispatchState(TypedDict):
    tenant_id: str
    order_id: str
    proposal_id: str | None
    needs_approval: bool
    error: str | None
```

Graph:

```
start
  → load_order
  → lock_order          # SET NX lock:order:{tid}:{id}
  → solve               # tools + solver; write DispatchProposal
  → policy_branch
        → auto: apply → emit events → unlock → end
        → hitl: interrupt(approve/reject) → apply | supersede → unlock → end
  → on error: unlock, proposal failed, route to DLQ-ish status
```

Human-in-the-loop: LangGraph **interrupt** before `apply`. Manager UI `POST /api/v1/dispatch/proposals/{id}/approve` resumes the run **or** simply calls `apply()` in Django if you do not persist graph checkpoints yet.

Pragmatic v1: **LangGraph in-process for auto path**; HITL = proposal row + REST approve (same `apply()`). Checkpointing (`PostgresSaver` / Redis) is the stretch so you can say “long-running workflow”.

Retries: solver timeout, ES down → retry node 2× then `status=failed` + notify ops. Do not auto-assign a random driver.

---

## 8. Kafka

`fleetiq-dispatch` consumes `fleetiq.orders` filtered `OrderCreated` / `OrderConfirmed` (you choose one; **Confirmed** is better so drafts do not dispatch).

Inbox: `processed_events` as in Phase D so one order ≠ two drivers.

On `apply()`:

```
transaction:
  assign_route(...)
  proposal.status = applied
  outbox DriverAssigned, OrderAssigned, RouteUpdated / RouteCreated
```

Do not produce those events from the LLM node directly.

---

## 9. Next.js `/dispatch`

Route group `(dispatch)`:

- `/dispatch` — queue of `pending` proposals (poll GraphQL or REST)
- `/dispatch/proposals/[id]` — map of candidate vehicles, scores, constraint fails for the ones rejected
- Approve / Reject buttons (RBAC `dispatcher` / `ops_manager`)
- `/routes` — assigned routes (already in B)

Show **explanation JSON**: distance, eta slack, capacity leftover. Optional LLM blurb clearly labeled “generated summary”.

WebSocket later can push new pending proposals (reuse Channels). Polling 3s is enough in G.

---

## 10. Failure cases to test

| Case | Expected |
|---|---|
| Two consumers get the same `OrderCreated` | One pending proposal; second is inbox skip |
| Approve twice | Second 409; assignment unique |
| Vehicle goes `maintenance` after propose, before approve | `apply()` re-checks hard constraints, `failed` |
| No candidate passes hard constraints | `pending` with empty chosen / `failed` + “unassigned” queue |
| Redis lock timeout | another worker may propose; unique pending index wins |
| ES empty | fall back to Postgres `Driver.objects.filter(status=available)` — solver still runs |

---

## 11. What you should be able to explain after G

- Why the LLM is the workflow/explainer, not the VRP.
- Hard constraints vs weighted cost, and why weights are stored on the proposal.
- ES as candidate generation, Redis as location/lock, Postgres as commit.
- Insertion heuristic vs OR-Tools wave.
- Idempotent `OrderConfirmed` handling and `assign_route` as a single writer.
- How H’s Operations Agent will **propose reassignment** by creating another `DispatchProposal`, not by UPDATE-ing drivers ad hoc.

---

## 12. Phase G done when

- [ ] `OrderConfirmed` → `DispatchProposal` with top 3 alternatives and a score breakdown
- [ ] Hard constraints reject bike-for-500kg and missing reefer skill
- [ ] Auto-assign path calls `assign_route` + outbox; map eventually shows that vehicle (with C simulator)
- [ ] HITL path: manager approve/reject in `/dispatch`
- [ ] LangGraph (or equivalent state machine) has explicit nodes; `solve` is code
- [ ] Redis lock + unique pending proposal prevent double assign
- [ ] Replay of the Kafka event does not assign a second driver
- [ ] OR-Tools wave command documented and runs on a 5-stop toy matrix

Next: **Phase H** — Operations Agent (“Why are deliveries delayed today?” / “Why is shipment #4521 delayed?”) with tools over Postgres, Redis, Mongo, ES knowledge, and `propose_reassignment` → `DispatchProposal` + the same HITL.
