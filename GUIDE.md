# Text-to-SQL v2 — Local Setup & Walkthrough Guide

A microservice that translates natural-language questions into PostgreSQL SQL, executes them against a school ERP database, and returns a human-readable summary. Every query is scoped to a `school_id` so no tenant can read another's data.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Project Structure](#2-project-structure)
3. [Architecture Overview](#3-architecture-overview)
4. [First-time Setup](#4-first-time-setup)
5. [Environment Variables](#5-environment-variables)
6. [Running the API Locally](#6-running-the-api-locally)
7. [Using the Debug UI](#7-using-the-debug-ui)
8. [Running Tests](#8-running-tests)
9. [Cloudflare Worker (Edge)](#9-cloudflare-worker-edge)
10. [Useful Scripts](#10-useful-scripts)

---

## 1. Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | ≥ 3.12 | [python.org](https://python.org) |
| uv | latest | `pip install uv` or `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node.js | ≥ 18 | [nodejs.org](https://nodejs.org) (only needed for the Cloudflare Worker) |
| PostgreSQL | any | Neon free tier works; `DB_URL` in `.env` |

---

## 2. Project Structure

```
text-sql-v2/
├── core/
│   ├── models/          # Pydantic schemas (query, intent, sql, result)
│   ├── schema_layer/    # GraphStore — loads db/schema_index.json into NetworkX
│   ├── retrieval_layer/ # SemanticMapper → TraversalEngine → QueryGraphPlanner → IntentClassifier
│   ├── generation_layer/# SQLClauseBuilder → OutputValidator → ValueExtractor → SQLGenerator
│   ├── execution_layer/ # SQLRunner (safety gate + school_id injection) + ResultSummarizer
│   ├── pipeline/        # LangGraph StateGraph wiring all layers together
│   └── api/
│       ├── middleware/  # X-Internal-Token auth + in-process rate limit
│       ├── routes/      # /health  /metrics  /schema/tables  /query  /query/plan
│       └── main.py      # FastAPI app + lifespan (loads graph + pipeline on startup)
│
├── api/
│   └── index.py         # Vercel entry point (re-exports app from core/api/main.py)
│
├── db/
│   ├── schema.sql        # Source-of-truth DDL
│   └── schema_index.json # Pre-built graph (committed; rebuilt via scripts/build_graph.py)
│
├── debug/
│   └── server.py         # Local-only debug UI server (requires DEBUG=true)
│
├── edge/
│   ├── src/index.ts      # Cloudflare Worker (auth + KV rate limit + proxy)
│   ├── wrangler.toml     # Worker config
│   └── package.json
│
├── scripts/
│   ├── build_graph.py    # Introspects live DB → writes db/schema_index.json
│   └── seed_db.py        # Seeds test data
│
├── tests/
│   ├── unit/             # Layer-isolated tests (mock DB + LLM)
│   ├── integration/      # Pipeline + API route tests (mock DB)
│   └── e2e/              # Full question bank against live DB
│
├── pyproject.toml        # Python dependencies (managed by uv)
├── requirements.txt      # Pinned lockfile (generated; safe for pip install)
├── .env.example          # All env vars documented
└── CLAUDE.md             # AI assistant instructions (architecture constraints)
```

---

## 3. Architecture Overview

Requests flow through five strictly downward layers — no layer imports above itself:

```
Browser / Dashboard
        │  Authorization: Bearer <DASHBOARD_API_KEY>
        ▼
Cloudflare Worker  (edge/src/index.ts)
  • Validates Bearer token
  • KV sliding-window rate limit (60 req/min per user)
  • Strips Authorization header
  • Injects X-Internal-Token
  • Forwards to FastAPI
        │
        ▼
FastAPI  (core/api/)
  • InternalTokenMiddleware  → validates X-Internal-Token
  • InProcessRateLimitMiddleware → failsafe in-process rate limit
        │
        ▼
LangGraph Pipeline  (core/pipeline/graph.py)
  planner → classifier → generator → validator → executor → summarizer
        │
        ▼
PostgreSQL (Neon)
  All queries have AND institute_id = '<school_id>' injected at execution time
```

### Security invariants

- Only `SELECT` statements are allowed — the safety gate strips quoted literals before checking for forbidden keywords, preventing bypass via embedded strings
- `school_id` is validated as a UUID before injection; injection happens in `execution_layer/runner.py` only, never in the clause builder
- `X-Internal-Token` uses `hmac.compare_digest` to prevent timing-oracle attacks
- `LIMIT` is always appended; default 100

---

## 4. First-time Setup

```bash
# 1. Clone and enter the repo
git clone <repo-url>
cd text-sql-v2

# 2. Install Python dependencies (creates .venv automatically)
uv sync

# 3. Copy environment template and fill in your values
cp .env.example .env
# edit .env — at minimum set DB_URL, LLM_MODEL, and the matching API key

# 4. Apply the schema to your database (skip if DB already has it)
psql "$DB_URL" -f db/schema.sql

# 5. (Optional) Seed test data
uv run python scripts/seed_db.py

# 6. Rebuild the schema graph (only needed after schema changes)
uv run python scripts/build_graph.py
# This overwrites db/schema_index.json — commit the result
```

> **Note:** `db/schema_index.json` is already committed. You only need to re-run `build_graph.py` if you change `db/schema.sql`.

---

## 5. Environment Variables

Copy `.env.example` to `.env` and set:

| Variable | Required | Description |
|----------|----------|-------------|
| `DB_URL` | Yes | PostgreSQL connection string (`postgresql://user:pass@host/db`) |
| `LLM_MODEL` | Yes | LiteLLM model string, e.g. `openai/gpt-4o-mini` |
| `GROQ_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | Yes* | API key matching your `LLM_MODEL` provider |
| `INTERNAL_SECRET` | Yes | Shared secret between Worker and FastAPI |
| `SCHEMA_PATH` | No | Path to schema graph JSON; default `db/schema_index.json` |
| `DEBUG` | No | Set `true` to enable the debug UI server; **never set in production** |
| `DEBUG_PORT` | No | Port for debug server; default `9000` |
| `BACKEND_URL` | No | Backend URL for debug server to proxy to; default `http://localhost:8000` |

---

## 6. Running the API Locally

```bash
# Start FastAPI with hot-reload on port 8000
uv run uvicorn core.api.main:app --reload --port 8000
```

The server will:
1. Load `db/schema_index.json` into a NetworkX graph (logged on startup)
2. Build the LangGraph pipeline
3. Start listening on `http://localhost:8000`

### Available endpoints

| Method | Path | Auth required | Description |
|--------|------|--------------|-------------|
| `GET` | `/health` | No | Graph loaded + DB reachable + uptime |
| `GET` | `/metrics` | Yes | Rolling avg latency, cost, rule/LLM hit rates |
| `GET` | `/schema/tables` | Yes | All tables + column names from loaded graph |
| `POST` | `/query` | Yes | Full pipeline — returns NL summary + token cost |
| `POST` | `/query/plan` | Yes | Dry-run — returns query plan + intent, no DB execution |

All routes except `/health` require the header `X-Internal-Token: <INTERNAL_SECRET>`.

### Quick smoke test

```bash
# Health (no auth)
curl http://localhost:8000/health

# Full query
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -H "X-Internal-Token: $INTERNAL_SECRET" \
  -d '{"query": "how many students are enrolled", "school_id": "<your-school-uuid>", "limit": 10}'

# Plan only (no DB hit)
curl -X POST http://localhost:8000/query/plan \
  -H "Content-Type: application/json" \
  -H "X-Internal-Token: $INTERNAL_SECRET" \
  -d '{"query": "list all teachers", "school_id": "<your-school-uuid>"}'
```

---

## 7. Using the Debug UI

The debug UI is a local single-file HTTP server that provides a browser form for testing the pipeline without writing curl commands.

**Requirements:** `DEBUG=true` in your `.env` and the FastAPI server running on port 8000.

```bash
# Terminal 1 — start FastAPI
uv run uvicorn core.api.main:app --reload --port 8000

# Terminal 2 — start debug UI
DEBUG=true uv run python debug/server.py
```

Then open **http://localhost:9000** in your browser.

### UI controls

| Control | Description |
|---------|-------------|
| **Query** textarea | Natural-language question to ask |
| **School ID** | UUID of the school to scope results to |
| **Limit** | Max rows to return (default 50) |
| **Plan Only** | Calls `POST /query/plan` — shows the query plan and classified intent, no SQL executed |
| **Full Query** | Calls `POST /query` — runs the full pipeline, shows NL summary + token cost |
| **Health Check** | Calls `GET /health` — shows DB reachability and graph status |

The debug server proxies all calls through `/proxy/*` to the local FastAPI, automatically injecting the `X-Internal-Token` header (read from `INTERNAL_SECRET` in your `.env`).

> The debug server is stdlib-only (`http.server`, `urllib`) — no extra dependencies.

---

## 8. Running Tests

```bash
# All tests
uv run pytest

# Unit tests only (no DB, no LLM — fast)
uv run pytest tests/unit/ -v

# Integration tests (mocked DB + LLM)
uv run pytest tests/integration/ -v

# Single test file
uv run pytest tests/unit/test_schema_layer.py -v

# E2E question bank (requires live DB + LLM + a real school UUID)
TEST_SCHOOL_ID=<uuid> uv run pytest tests/e2e/ -v --tb=short
```

### Test layout

| Suite | What it tests | DB / LLM |
|-------|--------------|----------|
| `tests/unit/` | Each layer in isolation | Mocked |
| `tests/integration/test_pipeline.py` | Full LangGraph pipeline | Mocked |
| `tests/integration/test_api_routes.py` | All 5 API routes + auth + rate limit | Mocked |
| `tests/e2e/` | 40+ NL questions, full round-trip | Live |

---

## 9. Cloudflare Worker (Edge)

The Worker sits in front of the FastAPI backend. It handles public-facing auth, rate limiting, and CORS so the backend only needs to validate `X-Internal-Token`.

### Local development

```bash
cd edge
npm install

# Dev mode — proxies to local FastAPI on port 8000
wrangler dev --local
```

Test it:

```bash
# Valid bearer → forwarded to backend
curl -H "Authorization: Bearer test-key" http://localhost:8787/health

# Missing auth → 401
curl http://localhost:8787/health

# Rate limit: send 61 requests quickly → 429 on the 61st
```

### Deploying to Cloudflare

```bash
cd edge

# Set secrets (not stored in wrangler.toml)
wrangler secret put DASHBOARD_API_KEY   # Bearer token the dashboard sends
wrangler secret put INTERNAL_SECRET     # Must match FastAPI's INTERNAL_SECRET
wrangler secret put BACKEND_URL         # e.g. https://your-api.vercel.app
wrangler secret put DASHBOARD_ORIGIN    # e.g. https://your-dashboard.vercel.app

# Create KV namespace if not done yet
wrangler kv:namespace create RATE_LIMIT_KV
# Copy the id into wrangler.toml → [[kv_namespaces]] id = "..."

wrangler deploy
```

### What the Worker does

1. **CORS preflight** — responds to `OPTIONS` before auth check
2. **Bearer auth** — validates `Authorization: Bearer <DASHBOARD_API_KEY>`; returns 401 on mismatch
3. **KV rate limit** — sliding 60-second window; 60 requests per `X-User-ID` (or `"anonymous"`); returns 429 when exceeded
4. **Header rewrite** — removes `Authorization`, injects `X-Internal-Token`
5. **Proxy** — forwards to `BACKEND_URL + pathname`; copies response with CORS headers

---

## 10. Useful Scripts

### Rebuild the schema graph

Run after any `db/schema.sql` change:

```bash
uv run python scripts/build_graph.py
git add db/schema_index.json
git commit -m "chore: rebuild schema graph"
```

The graph is a NetworkX DiGraph stored as JSON. Nodes are `tbl_{table}` and `col_{table}.{column}`. The API loads this file on startup — no live DB introspection at runtime.

### Seed test data

```bash
uv run python scripts/seed_db.py
```

Inserts a test school and sample rows for unit/integration testing.

### Generate a fresh requirements.txt

```bash
uv pip compile pyproject.toml --extra dev -o requirements.txt
```

Use this after updating `pyproject.toml`. The `requirements.txt` in the repo is the pinned lockfile for environments that use plain `pip install -r requirements.txt` instead of `uv`.

---

## Quick-start cheatsheet

```bash
# 1. Install
uv sync

# 2. Configure
cp .env.example .env  # fill in DB_URL + LLM_MODEL + INTERNAL_SECRET

# 3. Run API
uv run uvicorn core.api.main:app --reload --port 8000

# 4. Open debug UI (separate terminal)
DEBUG=true uv run python debug/server.py
# → http://localhost:9000

# 5. Run tests
uv run pytest
```
