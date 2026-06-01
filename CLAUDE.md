# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Text-to-SQL v2 — a private microservice that translates natural language queries into PostgreSQL SQL, executes them, and returns a human-readable summary with LLM token cost. Designed for a SaaS school ERP dashboard. Every query is scoped to a `school_id`.

**Deployment change from PRD:** FastAPI is hosted on **Vercel** (serverless, not Fly.io). This affects the Dockerfile and `deploy/` config — use `vercel.json` with a Python serverless function entry point instead of `fly.toml`.

## Commands

```bash
# Install dependencies
uv sync

# Run FastAPI locally
uv run uvicorn core.api.main:app --reload --port 8000

# Run debug UI (requires DEBUG=true in .env)
uv run python debug/server.py

# Build schema graph (run after applying schema.sql)
uv run python scripts/build_graph.py

# Seed database
uv run python scripts/seed_db.py

# Run all tests
uv run pytest

# Run a single test file
uv run pytest tests/unit/test_schema_layer.py -v

# Run unit tests only
uv run pytest tests/unit/ -v

# Run integration tests
uv run pytest tests/integration/ -v

# Run e2e question bank
uv run pytest tests/e2e/ -v

# Edge Worker (Cloudflare)
cd edge && wrangler dev        # local dev against local FastAPI
cd edge && wrangler deploy     # deploy to Cloudflare
```

## Architecture

Four strictly downward layers — no cross-layer imports except top-down:

```
API Layer  →  Execution Layer  →  Generation Layer  →  Retrieval Layer  →  Schema Layer
```

### Layer responsibilities

| Layer | Dir | Key class | What it does |
|---|---|---|---|
| Schema | `core/schema_layer/` | `GraphStore` | Loads `db/schema_index.json` into a NetworkX DiGraph at startup; singleton for API lifetime |
| Retrieval | `core/retrieval_layer/` | `QueryGraphPlanner` | NL entity → graph traversal → `QueryPlan`; `IntentClassifier` uses rule engine (≥0.75 confidence) with LLM fallback |
| Generation | `core/generation_layer/` | `SQLGenerator` | `QueryIntentJSON` → `SQLResult` via deterministic clause builder + optional LLM value extraction + 7-rule validation |
| Execution | `core/execution_layer/` | `SQLRunner` | Injects `AND institute_id = $school_id`, safety-gates SELECT-only, executes via psycopg3; `ResultSummarizer` converts rows → NL summary |
| Pipeline | `core/pipeline/graph.py` | `StateGraph` | LangGraph wiring: planner → classifier → generator → validator → executor → summarizer (conditional edge on validation result) |
| API | `core/api/` | FastAPI app | 5 routes; `auth.py` middleware validates `X-Internal-Token`; lifespan loads graph on startup |
| Edge | `edge/` | Cloudflare Worker | Auth (Bearer), per-user KV rate limit, CORS, strips Auth header, injects `X-Internal-Token`, forwards to backend |

### LangGraph pipeline state

`PipelineState` TypedDict in `core/pipeline/graph.py` carries: `query`, `school_id`, `limit`, `query_plan`, `intent`, `sql_result`, `run_result`, `summary`, `token_usage`, `error`.

Token usage is accumulated across all LLM nodes via LangGraph `RunnableConfig` callbacks and returned in every `QueryResponse`.

### Pydantic models (`core/models/`)

- `query.py` — `ResolvedEntity`, `TraversalResult`, `QueryPlan`
- `intent.py` — `QueryIntentJSON` (do not modify after initial definition)
- `sql.py` — `SQLResult`
- `result.py` — `QueryRunResult`, `TokenUsage`, `QueryResponse`

`QueryResponse` never includes raw rows — summary only.

### School scoping

`school_id` injection (`AND institute_id = $school_id`) happens in `execution_layer/runner.py`, not in the clause builder. The clause builder generates generic SQL.

### Schema graph

Built by `scripts/build_graph.py` from a live Neon DB → saved as `db/schema_index.json` → committed. Node IDs: `tbl_{table_name}`, `col_{table}.{column}`. Rebuild is a CLI operation, not an API call.

### Security

- `X-Internal-Token` validated in `middleware/auth.py` — all routes except `/health` require it
- Safety gate in `runner.py` strips quoted literals before checking for forbidden SQL keywords (prevents false positives from v1)
- LIMIT always appended; default 100

## Environment Variables

See `.env.example`. Key vars: `DB_URL`, `LLM_MODEL`, `INTERNAL_SECRET`, `DEBUG`.

`DEBUG=true` enables the local debug UI at `debug/server.py` — never set in production.

## Vercel Deployment

The FastAPI app is deployed to Vercel as a serverless Python function. Use `vercel.json` with `api/index.py` as the entry point (re-exporting the FastAPI `app`). The `deploy/` directory holds Vercel config instead of Fly.io `fly.toml`.

**Important:** The in-memory NetworkX graph (`GraphStore`) must be pre-built and committed as `db/schema_index.json`. Vercel serverless functions are stateless — the graph is loaded from the JSON file on each cold start (no CLI rebuild at runtime).

## Testing Strategy

- Unit tests mock the graph store and LLM calls — test each layer in isolation
- Integration tests hit a real Neon dev branch DB
- E2E question bank (`tests/e2e/test_question_bank.py`) — 40+ NL questions, all intent categories, full pipeline against live DB
