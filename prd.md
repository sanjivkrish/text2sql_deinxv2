# Text-to-SQL v2 — Production Plan

**Date:** 2026-06-01  
**Author:** Sujay S  
**Predecessor:** `deinx_prjv1` (SKG_v1 pipeline, 12 phases, 409 tests)

---

## 1. Vision

A **private text-to-SQL microservice** that runs as a feature endpoint for a SaaS school ERP dashboard. Natural language queries from dashboard users are translated into PostgreSQL SQL, executed against the school's data, and returned as a **human-readable summary** — along with **LLM token cost** for the request. Raw rows never leave the backend.

The service is school-scoped: every request carries a `school_id`. The backend enforces `WHERE institute_id = $school_id` on all queries. Cross-school authorization is the ERP dashboard's responsibility — this service trusts the `school_id` it receives.

**What changes from v1:**
- Fresh schema with new nomenclature (DDL will be provided separately — not in this spec)
- Flat 4-layer architecture instead of 12 incremental phases
- Edge gateway (Cloudflare Worker) as the SaaS integration point
- Output is a **summary + token cost**, not raw SQL or rows
- **LangGraph** replaces CrewAI for pipeline orchestration
- Debug UI for local developer testing
- Production deployment from day one (Fly.io + Neon + Cloudflare)

**What stays from v1:**
- Graph-based schema knowledge (SKG approach) — the core accuracy driver
- Rule engine → LLM fallback classification pattern
- Deterministic clause builder for SQL assembly
- Pydantic v2 contracts, psycopg3, uv, pytest

---

## 2. System Architecture

```
SaaS Dashboard (host app)
        │
        │  HTTPS + Bearer token
        │  Body: { query, school_id }
        ▼
┌───────────────────────────┐
│   Cloudflare Worker       │  ← Edge Layer (TypeScript)
│   - Auth: Bearer token    │
│   - Rate limit: per user  │
│   - CORS for dashboard    │
│   - Strip internal hdrs   │
└───────────┬───────────────┘
            │  Internal HTTPS (forwarded request)
            ▼
┌───────────────────────────┐
│   FastAPI Backend         │  ← Python Service (Fly.io, single region)
│   LangGraph pipeline      │
│   - /query                │
│   - /query/plan           │
│   - /schema/tables        │
│   - /health               │
│   - /metrics              │
└───────────┬───────────────┘
            │
     ┌──────┴──────┐
     ▼             ▼
┌─────────┐  ┌──────────────┐
│  Neon   │  │  NetworkX    │
│PostgreSQL│  │  Graph Store │
│ (DB)    │  │  (in-memory) │
└─────────┘  └──────────────┘
```

**Edge layer** handles all public-facing concerns: auth, rate limiting, CORS, request forwarding. It never touches SQL or schema logic.

**Python backend** is not exposed to the internet — only the Cloudflare Worker's egress IPs can reach it (enforced via Fly.io firewall rules). It owns the entire text-to-SQL pipeline.

**School scoping** — the backend appends `AND institute_id = $school_id` to every generated query's WHERE clause before execution. It does not validate whether the requesting user is allowed to access that `school_id`; that check belongs to the ERP dashboard before it calls this service.

**Graph store** is loaded into memory at startup from a prebuilt file. Rebuilding requires running a CLI script — not an API call.

---

## 3. Database Schema

Schema DDL and domain map will be provided separately. They will follow the same relational structure as `deinx_prjv1` (hub tables + satellite tables, same FK topology, ~7 tables) with new nomenclature.

**What this service assumes:**
- One of the tables acts as the primary institution/school entity, with a primary key used as `school_id`
- All satellite tables have a foreign key referencing that institution table
- Column names, types, and exact relationships will be finalized when the DDL is provided
- `build_graph.py` will be run against the final schema to generate `schema_index.json` and the graph store

**Placeholder:** Once schema is provided, update `db/schema.sql`, run `scripts/build_graph.py`, and commit the generated `db/schema_index.json`.

---

## 4. LangGraph Pipeline

The text-to-SQL pipeline is modelled as a **LangGraph `StateGraph`**. Each node is a pure function that reads from and writes to a typed state dict. Token usage is accumulated across all LLM nodes and reported in the final response.

### Pipeline State

```python
class PipelineState(TypedDict):
    # Input
    query: str
    school_id: int
    limit: int

    # Intermediate
    query_plan: QueryPlan | None
    intent: QueryIntentJSON | None
    sql_result: SQLResult | None
    run_result: QueryRunResult | None

    # Output
    summary: str | None
    token_usage: TokenUsage | None
    error: str | None
```

### Graph Nodes

```
[planner] → [classifier] → [generator] → [validator] ──► [executor] → [summarizer]
                                               │
                                          (invalid)
                                               ▼
                                           [error_node]
```

| Node | Reads | Writes | LLM? |
|---|---|---|---|
| `planner` | `query`, `school_id` | `query_plan` | No |
| `classifier` | `query`, `query_plan` | `intent` | Fallback only |
| `generator` | `intent` | `sql_result` | Fallback only (value extraction) |
| `validator` | `sql_result`, `intent` | routes to executor or error | No |
| `executor` | `sql_result`, `school_id` | `run_result` | No |
| `summarizer` | `query`, `run_result` | `summary`, `token_usage` | Always |
| `error_node` | `error` | `summary`, `token_usage` | No |

The `executor` node injects `AND institute_id = $school_id` into the WHERE clause before running the query. The `summarizer` node makes the only guaranteed LLM call — it converts query results into a natural language summary and reports token usage for the entire request.

### Token Cost Tracking

All LLM calls in the pipeline (classifier fallback, value extractor, summarizer) use LangGraph's `RunnableConfig` callback system to capture `usage_metadata`. Token counts are accumulated in a `TokenUsage` model and returned with the response.

```python
class TokenUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float   # based on model pricing at build time
```

Cost estimation uses a static per-model rate table. It is approximate — exact billing is the LLM provider's.

---

## 5. Python Backend Architecture

Four clean layers. Each layer exports one public class and one `__init__.py`. No cross-layer imports except downward (API → Execution → Generation → Retrieval → Schema).

### Layer 1 — Schema Layer
**Purpose:** Build and serve the knowledge graph from PostgreSQL schema.

| File | Class | Responsibility |
|---|---|---|
| `schema_layer/extractor.py` | `SchemaExtractor` | Introspect PostgreSQL → `schema_index.json` |
| `schema_layer/graph_builder.py` | `GraphBuilder` | `schema_index.json` → NetworkX DiGraph |
| `schema_layer/graph_store.py` | `GraphStore` | Persist/load graph; singleton for API lifetime |

Graph node IDs follow the same deterministic pattern as v1:
- Table nodes: `tbl_{table_name}`
- Column nodes: `col_{table}.{column}`
- FK edges carry `join_sql` attributes

### Layer 2 — Retrieval Layer
**Purpose:** Understand query intent and resolve it to a QueryPlan.

| File | Class | Responsibility |
|---|---|---|
| `retrieval_layer/semantic_mapper.py` | `SemanticMapper` | NL entity → table/column candidates |
| `retrieval_layer/traversal.py` | `TraversalEngine` | Graph BFS/DFS → join paths |
| `retrieval_layer/query_planner.py` | `QueryGraphPlanner` | Assemble `QueryPlan` from mapper + traversal |
| `retrieval_layer/intent_classifier.py` | `IntentClassifier` | Rule engine (≥0.75) → LLM fallback → `QueryIntentJSON` |

Intent categories: `POINT_LOOKUP | FILTERED_LIST | AGGREGATION | COMPARATIVE | TEMPORAL`

### Layer 3 — Generation Layer
**Purpose:** Transform `QueryIntentJSON` into validated SQL.

| File | Class | Responsibility |
|---|---|---|
| `generation_layer/clause_builder.py` | `SQLClauseBuilder` | Deterministic SELECT/FROM/JOIN/WHERE/ORDER/LIMIT assembly |
| `generation_layer/value_extractor.py` | `ValueExtractor` | Single LLM call to fill empty filter values |
| `generation_layer/output_validator.py` | `OutputValidator` | 7-rule post-generation validation → `ValidationReport` |
| `generation_layer/sql_generator.py` | `SQLGenerator` | Orchestrates builder + extractor + validator → `SQLResult` |

SQL injection mitigation lives in `clause_builder.py`. LIMIT is always appended (default 100, configurable). School-ID injection happens in the executor node, not the clause builder — the clause builder generates generic SQL.

### Layer 4 — Execution Layer
**Purpose:** Run SQL safely, summarize results, track token cost.

| File | Class | Responsibility |
|---|---|---|
| `execution_layer/runner.py` | `SQLRunner` | Safety gate (SELECT-only) + school_id injection + psycopg3 execution |
| `execution_layer/summarizer.py` | `ResultSummarizer` | LLM call: rows → natural language summary + token usage |

Safety gate normalizes SQL (strips quoted literals) before token-checking forbidden keywords — prevents false-positive bug from v1.

---

## 6. Pydantic Contracts

All inter-layer data is typed via Pydantic v2 models in `core/models/`.

```python
# models/query.py
class ResolvedEntity(BaseModel):
    raw_text: str
    table: str
    column: str | None
    confidence: float

class TraversalResult(BaseModel):
    path: list[str]
    join_sql: list[str]
    hop_count: int

class QueryPlan(BaseModel):
    resolved_entities: list[ResolvedEntity]
    join_paths: list[TraversalResult]
    recommended_tables: list[str]
    recommended_joins: list[str]
    confidence: float

# models/intent.py  (do not modify after initial definition)
class QueryMetadata(BaseModel):
    raw_query: str
    primary_domain: str
    operational_intent: str
    confidence: float

class FilterCondition(BaseModel):
    table: str
    column: str
    operator: str
    value: str
    value_type: str

class Aggregation(BaseModel):
    table: str
    column: str
    function: str

class Ordering(BaseModel):
    table: str
    column: str
    direction: str

class StructuralPlan(BaseModel):
    tables: list[str]
    join_conditions: list[str]
    select_columns: list[str]

class QueryIntentJSON(BaseModel):
    query_metadata: QueryMetadata
    structural_plan: StructuralPlan
    filters: list[FilterCondition]
    aggregations: list[Aggregation]
    ordering: list[Ordering]

# models/sql.py
class SQLResult(BaseModel):
    sql: str
    confidence_score: float
    warnings: list[str]
    value_extractions: dict[str, str]

# models/result.py
class QueryRunResult(BaseModel):
    row_count: int
    execution_time_ms: float
    sql: str                    # school_id-injected SQL that actually ran

class TokenUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float

class QueryResponse(BaseModel):     # API response — what the dashboard receives
    query: str
    school_id: int
    summary: str                    # LLM-generated natural language summary
    token_usage: TokenUsage
    confidence: float
    warnings: list[str]
    timing: dict[str, float]        # plan_ms, classify_ms, generate_ms, execute_ms, summarize_ms, total_ms
```

Note: raw rows are **not** in `QueryResponse`. They exist only inside the pipeline state and are discarded after the summarizer runs.

---

## 7. FastAPI API Layer

### Middleware
- `middleware/auth.py` — validates `X-Internal-Token` header (injected by Cloudflare Worker); rejects with 401 if missing or wrong
- `middleware/rate_limit.py` — in-process failsafe rate limit; primary is Cloudflare KV

### Routes

#### `POST /query`
Full pipeline: plan → classify → generate → validate → execute → summarize.

Request:
```json
{
  "query": "Show me all students from Grade 10 with overdue fees",
  "school_id": 2,
  "limit": 50
}
```

Response (`QueryResponse`):
```json
{
  "query": "Show me all students from Grade 10 with overdue fees",
  "school_id": 2,
  "summary": "There are 12 Grade 10 students with overdue fees at this school. The oldest overdue fee is from January 2025, and the total outstanding amount across all 12 students is ₹48,300.",
  "token_usage": {
    "input_tokens": 312,
    "output_tokens": 87,
    "total_tokens": 399,
    "estimated_cost_usd": 0.00041
  },
  "confidence": 0.91,
  "warnings": [],
  "timing": {
    "plan_ms": 12,
    "classify_ms": 8,
    "generate_ms": 6,
    "execute_ms": 43,
    "summarize_ms": 620,
    "total_ms": 689
  }
}
```

Error responses:
- `400` — blocked by safety gate or validation failure
- `422` — malformed request body
- `429` — rate limit exceeded
- `500` — pipeline error: `{"error": "...", "detail": "..."}`

#### `POST /query/plan`
Returns `QueryPlan` + `QueryIntentJSON` only — no execution, no LLM summarization. Used for dry-run / preview. No token cost incurred beyond classifier fallback.

#### `GET /schema/tables`
Returns table names and column names from `schema_index.json`. Used by dashboard for query autocomplete.

#### `GET /health`
```json
{ "status": "ok", "graph_loaded": true, "db_reachable": true, "uptime_s": 3820 }
```

#### `GET /metrics`
```json
{
  "requests_total": 1420,
  "requests_success": 1398,
  "requests_error": 22,
  "avg_latency_ms": 312,
  "avg_token_cost_usd": 0.00038,
  "rule_engine_hit_rate": 0.83,
  "llm_fallback_rate": 0.17
}
```

---

## 8. Debug UI

A local-only debug server (`debug/server.py`) for developer testing — never deployed to production. Gated by `DEBUG=true` in `.env`.

**Purpose:** Test the full pipeline from a browser without needing the SaaS dashboard or Cloudflare Worker.

**Interface:**
- Input form: query text field + school_id selector
- Three buttons: **Plan Only** (calls `/query/plan`) | **Full Query** (calls `/query`) | **Health Check**
- Output panels:
  - **Summary** — the LLM-generated response
  - **Token Cost** — input/output/total tokens + estimated USD
  - **Pipeline Trace** — collapsible sections for QueryPlan, QueryIntentJSON, raw SQL, row count, per-stage timing
  - **Warnings** — validation warnings if any

Implementation: minimal stdlib `http.server` + embedded HTML/JS (same pattern as v1 `visual_debug.py`). No npm, no build step, runs as `python debug/server.py`.

---

## 9. Edge Layer — Cloudflare Worker

Single TypeScript Worker. Lives in `edge/` in the workspace, deployed separately via Wrangler.

### Responsibilities
1. **Auth** — validates `Authorization: Bearer <DASHBOARD_API_KEY>` against `env.DASHBOARD_API_KEY`. Returns 401 on mismatch.
2. **Rate limiting** — increments per `X-User-ID` counter in Cloudflare KV. Returns 429 after threshold (default 60 req/min).
3. **Request forwarding** — strips `Authorization` header, injects `X-Internal-Token: env.INTERNAL_SECRET`, forwards to `env.BACKEND_URL`.
4. **CORS** — adds `Access-Control-Allow-Origin: env.DASHBOARD_ORIGIN` to responses.
5. **Error passthrough** — streams backend error responses as-is.

Secrets (set via `wrangler secret put`):
- `DASHBOARD_API_KEY` — what the SaaS dashboard sends
- `INTERNAL_SECRET` — what the Worker sends to Python backend
- `BACKEND_URL` — Fly.io app URL
- `DASHBOARD_ORIGIN` — SaaS dashboard origin for CORS

---

## 10. Security Model

| Threat | Mitigation |
|---|---|
| Unauthorized dashboard calls | Cloudflare Worker validates Bearer token |
| Direct backend access bypassing edge | Fly.io firewall: only Cloudflare IP ranges allowed |
| Cross-school data access | Backend appends `AND institute_id = $school_id` to every query |
| SQL injection in filter values | `_quote_string()` in clause builder + parameterized school_id injection |
| Non-SELECT SQL | Safety gate tokenizes after stripping quoted literals |
| Internal secret leakage | Stored in Cloudflare secrets + Fly.io env only |
| Rate abuse | Cloudflare KV per-user counter + in-process failsafe |
| Response data leakage | Raw rows never returned in API response — summary only |

---

## 11. Directory Structure

```
text_sql_v2/
├── CLAUDE.md
├── pyproject.toml              # uv-managed; langgraph, langchain-core, litellm, fastapi, psycopg[binary], networkx, pydantic
├── .env.example                # DB_URL, LLM_MODEL, INTERNAL_SECRET, DEBUG
├── db/
│   ├── schema.sql              # provided separately — apply before running build_graph.py
│   ├── schema_index.json       # auto-generated; committed after build
│   └── seeds/                  # CSV seed data (provided separately)
├── core/
│   ├── pipeline/
│   │   └── graph.py            # LangGraph StateGraph definition + node wiring
│   ├── schema_layer/
│   │   ├── __init__.py
│   │   ├── extractor.py
│   │   ├── graph_builder.py
│   │   └── graph_store.py
│   ├── retrieval_layer/
│   │   ├── __init__.py
│   │   ├── semantic_mapper.py
│   │   ├── traversal.py
│   │   ├── query_planner.py
│   │   └── intent_classifier.py
│   ├── generation_layer/
│   │   ├── __init__.py
│   │   ├── clause_builder.py
│   │   ├── value_extractor.py
│   │   ├── output_validator.py
│   │   └── sql_generator.py
│   ├── execution_layer/
│   │   ├── __init__.py
│   │   ├── runner.py
│   │   └── summarizer.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── query.py
│   │   ├── intent.py
│   │   ├── sql.py
│   │   └── result.py
│   └── api/
│       ├── main.py
│       ├── routes/
│       │   ├── query.py
│       │   ├── schema.py
│       │   └── health.py
│       └── middleware/
│           ├── auth.py
│           └── rate_limit.py
├── debug/
│   └── server.py               # local-only debug UI (DEBUG=true only)
├── edge/
│   ├── src/
│   │   └── index.ts
│   ├── wrangler.toml
│   └── package.json
├── tests/
│   ├── unit/
│   │   ├── test_schema_layer.py
│   │   ├── test_retrieval_layer.py
│   │   ├── test_generation_layer.py
│   │   └── test_execution_layer.py
│   ├── integration/
│   │   ├── test_pipeline.py
│   │   └── test_api_routes.py
│   └── e2e/
│       └── test_question_bank.py
├── scripts/
│   ├── build_graph.py
│   └── seed_db.py
└── deploy/
    ├── fly.toml
    └── Dockerfile
```

---

## 12. Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| Package manager | uv |
| Pipeline orchestration | LangGraph (`langgraph`, `langchain-core`) |
| LLM calls | LiteLLM (direct, no CrewAI) |
| API framework | FastAPI + uvicorn |
| Graph | NetworkX |
| DB driver | psycopg (v3, binary) |
| Validation models | Pydantic v2 |
| Edge runtime | Cloudflare Workers (TypeScript) |
| Edge rate limiting | Cloudflare KV |
| Managed PostgreSQL | Neon (serverless, dev + prod branches) |
| Python deployment | Fly.io (single region, close to Neon) |
| Testing | pytest |
| CI | GitHub Actions |

---

## 13. Implementation Phases

### Phase 1 — Workspace Bootstrap (Day 1)
- Init new git repo, `pyproject.toml` with `uv`, `CLAUDE.md`, `.env.example`
- Create Neon project (dev branch)
- Apply `schema.sql` once provided; run `seed_db.py` once seeds are provided
- Verify row counts and FK integrity

**Deliverable:** Empty workspace ready. DB pending schema delivery.

### Phase 2 — Schema Layer (Days 2–3)
- TDD: `SchemaExtractor` → `schema_index.json`
- TDD: `GraphBuilder` → NetworkX DiGraph with table/column/FK nodes
- TDD: `GraphStore` → persist to `db/schema_index.json`, singleton load
- Run `build_graph.py`, commit generated file

**Deliverable:** Graph built and persisted. 30+ unit tests passing.

### Phase 3 — Retrieval Layer (Days 4–6)
- TDD: `SemanticMapper`, `TraversalEngine`, `QueryGraphPlanner`, `IntentClassifier`
- Wire into end-to-end retrieval test: NL query → `QueryPlan` + `QueryIntentJSON`

**Deliverable:** 60+ tests passing.

### Phase 4 — Generation Layer (Days 7–8)
- TDD: `SQLClauseBuilder`, `ValueExtractor`, `OutputValidator`, `SQLGenerator`

**Deliverable:** `QueryIntentJSON` → `SQLResult`. 50+ tests passing.

### Phase 5 — Execution Layer (Day 9)
- TDD: `SQLRunner` — safety gate + school_id injection + psycopg3
- TDD: `ResultSummarizer` — LLM call → summary + `TokenUsage`

**Deliverable:** Full pipeline: NL → SQL → rows → summary. 20+ tests.

### Phase 6 — LangGraph Pipeline (Day 10)
- Define `PipelineState` TypedDict
- Wire all nodes into `StateGraph` in `core/pipeline/graph.py`
- Conditional edge from `validator`: valid → executor | invalid → error_node
- Accumulate token usage across all LLM nodes via LangGraph callbacks

**Deliverable:** `graph.invoke({"query": ..., "school_id": ...})` returns `QueryResponse`.

### Phase 7 — API Layer (Days 11–12)
- FastAPI app with lifespan (graph load at startup)
- All 5 routes, auth middleware, in-process rate limit failsafe
- Integration tests for all routes

**Deliverable:** FastAPI app running locally, all routes tested.

### Phase 8 — Debug UI (Day 13)
- `debug/server.py` — stdlib HTTP server + embedded HTML
- Query form + school_id selector
- Panels: summary, token cost, pipeline trace (collapsible), warnings

**Deliverable:** `python debug/server.py` renders full pipeline output in browser.

### Phase 9 — Edge Worker (Day 14)
- Cloudflare Worker: auth, KV rate limit, forwarding, CORS
- Local test via `wrangler dev` → local FastAPI
- Deploy to Cloudflare dev environment

**Deliverable:** Edge Worker deployed and tested end-to-end locally.

### Phase 10 — Question Bank E2E Tests (Day 15)
- 40+ real NL questions covering all intent categories and domains
- Full pipeline against live Neon dev DB
- All produce valid summaries with `is_valid=True`

**Deliverable:** `tests/e2e/test_question_bank.py` — 100+ assertions, 0 failures.

### Phase 11 — Production Deployment (Day 16)
- Neon prod branch + seed
- Fly.io deploy + IP firewall (Cloudflare ranges only)
- Cloudflare Worker production deploy + secrets
- Smoke test: dashboard origin → Worker → Fly.io → Neon → summary response

**Deliverable:** Live production endpoint.

### Phase 12 — SaaS Dashboard Integration (Day 17)
- Provide team: `DASHBOARD_API_KEY`, Worker URL, request/response schema
- Validate CORS from dashboard origin
- Confirm `POST /query` round-trip from dashboard UI
- Document `/schema/tables` for autocomplete

**Deliverable:** Feature live in SaaS dashboard.

---

## 14. Performance Targets

| Metric | Target |
|---|---|
| Rule engine classification | < 10 ms |
| SQL generation (no LLM) | < 50 ms |
| LLM value extraction fallback | < 800 ms |
| DB execution | < 500 ms |
| LLM summarization | < 1 500 ms |
| Total end-to-end (rule path) | < 2 200 ms |
| Total end-to-end (LLM path) | < 3 500 ms |
| Edge overhead | < 30 ms |
| Classification accuracy | > 90% |
| Rule engine hit rate | > 75% |

---

## 15. Key Decisions and Rationale

| Decision | Rationale |
|---|---|
| LangGraph for orchestration | Stateful pipeline with conditional edges; cleaner than sequential calls; built-in callback system for token tracking |
| Output is summary only (no raw rows) | Dashboard shows insights, not data tables; reduces response payload; prevents raw data leakage |
| Token cost in every response | Transparency for the SaaS product; enables usage-based billing hooks later |
| school_id injected at executor node | Keeps clause builder generic and testable; scoping is a runtime concern, not a generation concern |
| Graph-based retrieval retained | Join-path accuracy on multi-table queries; proven in v1 |
| Edge on Cloudflare Worker | Auth + rate limiting without touching Python; global presence |
| Python on Fly.io (not Lambda) | Persistent graph in memory; Lambda cold start would reload graph per request |
| Neon for PostgreSQL | Dev/prod branch isolation; scales to zero in dev |
| LiteLLM direct (no CrewAI) | Model-agnostic; swap provider without code change; LangGraph handles orchestration instead |
| Debug UI excluded from production | No surface area; `DEBUG=true` gate ensures it can't be accidentally deployed |
| LIMIT always appended | Prevents unbounded queries |
| Graph rebuilt via CLI only | Keeps API stateless; schema changes are deliberate |

---

## 16. Out of Scope (v2 MVP)

- BM25 retrieval layer (planned for v3)
- Multi-tenant DB isolation (single DB, `institute_id` filter only)
- Streaming summaries (batch response only at MVP)
- Prediction / ML layer
- Fine-tuned domain models
- Long-term query memory
- Human-in-the-loop review
- OpenTelemetry / external monitoring
- Automatic schema migration
