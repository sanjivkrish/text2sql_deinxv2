# Text-to-SQL v2 — Session Roadmap

Each session is a self-contained deliverable. A future Claude instance can pick up any session cold by reading this file + the main plan (`2026-06-01-text-sql-v2.md`) + the schema (`DB_SCHEMA.md`).

**Main plan:** `docs/superpowers/plans/2026-06-01-text-sql-v2.md`

---

## Session 1 — Workspace Bootstrap + Schema Graph

**Covers:** Main plan Tasks 1–4 (Models, Extractor, Graph Builder, Graph Store + build_graph.py)

**Entry condition:** `uv` installed, Neon dev DB reachable, `DB_URL` in `.env`

**Steps:**
1. Run `uv sync` — verify no import errors
2. Implement Task 1: Pydantic models (`core/models/`)
3. Implement Task 2: `SchemaExtractor`
4. Implement Task 3: `GraphBuilder`
5. Implement Task 4: `GraphStore` + `scripts/build_graph.py`
6. Run `uv run python scripts/build_graph.py` — commit generated `db/schema_index.json`
7. Run `uv run pytest tests/unit/test_models.py tests/unit/test_schema_layer.py -v`

**Exit condition (done when):**
- `db/schema_index.json` committed and loadable
- `uv run pytest tests/unit/test_models.py tests/unit/test_schema_layer.py` → 12+ passed, 0 failed
- `git tag session-1-done`

**Carry-forward state:** `db/schema_index.json` is the artefact every later session depends on.

---

## Session 2 — Retrieval Layer

**Covers:** Main plan Tasks 5–8 (SemanticMapper, TraversalEngine, QueryGraphPlanner, IntentClassifier)

**Entry condition:** Session 1 done. `db/schema_index.json` exists.

**Steps:**
1. Implement Task 5: `SemanticMapper`
2. Implement Task 6: `TraversalEngine`
3. Implement Task 7: `QueryGraphPlanner`
4. Implement Task 8: `IntentClassifier`
5. Run `uv run pytest tests/unit/test_retrieval_layer.py -v`

**Exit condition:**
- Given any NL query string, `IntentClassifier.classify(query, plan)` returns a valid `QueryIntentJSON` with one of: `POINT_LOOKUP | FILTERED_LIST | AGGREGATION | COMPARATIVE | TEMPORAL`
- `uv run pytest tests/unit/test_retrieval_layer.py` → 19+ passed, 0 failed
- `git tag session-2-done`

**Carry-forward state:** All retrieval classes importable and tested. No DB or LLM calls needed at this layer except the LLM fallback path in `IntentClassifier` (which is only triggered when rule confidence < 0.75).

---

## Session 3 — Generation Layer

**Covers:** Main plan Tasks 9–11 (SQLClauseBuilder, OutputValidator, ValueExtractor, SQLGenerator)

**Entry condition:** Session 2 done.

**Steps:**
1. Implement Task 9: `SQLClauseBuilder` (deterministic, no LLM)
2. Implement Task 10: `OutputValidator` (7 rules, no LLM)
3. Implement Task 11: `ValueExtractor` + `SQLGenerator`
4. Run `uv run pytest tests/unit/test_generation_layer.py -v`

**Exit condition:**
- Given a `QueryIntentJSON`, `SQLGenerator.generate(intent, limit)` returns a `SQLResult` with valid SQL, soft-delete guards, and no injection vulnerabilities
- `uv run pytest tests/unit/test_generation_layer.py` → 17+ passed, 0 failed
- `git tag session-3-done`

**Carry-forward state:** `SQLGenerator` is the generation layer's single public entry point. Later sessions only call `SQLGenerator`, never the sub-components directly.

---

## Session 4 — Execution Layer

**Covers:** Main plan Tasks 12–13 (SQLRunner, ResultSummarizer)

**Entry condition:** Session 3 done. `.env` has `DB_URL` and `LLM_MODEL`.

**Steps:**
1. Implement Task 12: `SQLRunner` (safety gate + school_id injection + psycopg3)
2. Implement Task 13: `ResultSummarizer` (LiteLLM → NL summary + TokenUsage)
3. Run `uv run pytest tests/unit/test_execution_layer.py -v`

**Exit condition:**
- `SQLRunner._safety_check()` blocks all non-SELECT SQL; cannot be bypassed by quoting tricks
- `SQLRunner._inject_school_id()` injects `{table}.school_id = '{uuid}'` before LIMIT
- `ResultSummarizer.summarize()` returns `(str, TokenUsage)` from mocked LLM in tests
- `uv run pytest tests/unit/test_execution_layer.py` → 8+ passed, 0 failed
- `git tag session-4-done`

**Carry-forward state:** Both classes are importable. Real DB execution is tested in Session 5's integration tests.

---

## Session 5 — LangGraph Pipeline

**Covers:** Main plan Task 14 (pipeline/graph.py + integration test)

**Entry condition:** Sessions 1–4 done. All unit tests passing.

**Steps:**
1. Implement `core/pipeline/graph.py` — `PipelineState` TypedDict + all 7 nodes + conditional validator edge
2. Write `tests/integration/test_pipeline.py` with mocked DB + LLM
3. Run `uv run pytest tests/integration/test_pipeline.py -v`

**Exit condition:**
- `build_pipeline(schema_path, db_url).invoke({"query": ..., "school_id": ..., "limit": ...})` returns a state dict with `summary`, `token_usage`, and `error: None`
- Conditional edge routes to `error_node` when validation fails
- `uv run pytest tests/integration/test_pipeline.py` → 1+ passed, 0 failed
- `git tag session-5-done`

**Carry-forward state:** `build_pipeline()` is the single callable the API layer uses. Session 6 imports nothing else from the pipeline.

---

## Session 6 — FastAPI Application

**Covers:** Main plan Tasks 15–16 (middleware + all routes + app + integration tests)

**Entry condition:** Session 5 done. `build_pipeline()` importable.

**Steps:**
1. Implement Task 15: `middleware/auth.py` + `middleware/rate_limit.py`
2. Implement Task 16: `routes/health.py`, `routes/schema.py`, `routes/query.py`, `core/api/main.py`
3. Write `tests/integration/test_api_routes.py`
4. Run `uv run pytest tests/integration/ -v`
5. Smoke test: `uv run uvicorn core.api.main:app --reload --port 8000`

**Exit condition:**
- All 5 endpoints respond correctly: `GET /health`, `GET /metrics`, `GET /schema/tables`, `POST /query`, `POST /query/plan`
- Missing or wrong `X-Internal-Token` → 401
- `uv run pytest tests/integration/` → 5+ passed, 0 failed
- `git tag session-6-done`

**Carry-forward state:** FastAPI app is fully runnable. Session 7 only adds a local UI + edge worker on top of it.

---

## Session 7 — Debug UI + Cloudflare Worker

**Covers:** Main plan Tasks 17–18 (debug/server.py + edge/src/index.ts)

**Entry condition:** Session 6 done. `uvicorn core.api.main:app` starts without errors.

**Steps:**
1. Implement Task 17: `debug/server.py` (stdlib HTTP server + embedded HTML)
2. Manual test: `DEBUG=true uv run python debug/server.py` → open `http://localhost:9000`
3. Implement Task 18: `edge/src/index.ts` (Cloudflare Worker)
4. `cd edge && npm install && wrangler dev` → smoke test against local FastAPI
5. Deploy to Cloudflare dev: `wrangler deploy`

**Exit condition:**
- Debug UI renders in browser; Plan Only / Full Query / Health Check buttons work
- Cloudflare Worker in dev environment: valid Bearer → forwards to backend; invalid Bearer → 401; rate limit → 429
- `git tag session-7-done`

**Carry-forward state:** Worker URL noted in `.env.example` comment for Session 8.

---

## Session 8 — Vercel Deployment + E2E Tests

**Covers:** Main plan Tasks 19–20 (vercel.json + e2e question bank)

**Entry condition:** Session 6 done (FastAPI app working). Neon prod branch exists. `db/schema_index.json` built against prod schema.

**Steps:**
1. Implement Task 19: `vercel.json` at repo root, set Vercel env vars
2. `vercel --prod` → verify `GET /health` on production URL
3. Update Cloudflare Worker `BACKEND_URL` secret to Vercel prod URL
4. Implement Task 20: `tests/e2e/test_question_bank.py` with real school UUID
5. Run: `TEST_SCHOOL_ID=<uuid> uv run pytest tests/e2e/ -v --tb=short`
6. Smoke test full round-trip: Dashboard origin → Cloudflare Worker → Vercel → Neon

**Exit condition:**
- `GET https://<vercel-url>/health` returns `{"status":"ok","graph_loaded":true,"db_reachable":true,...}`
- `TEST_SCHOOL_ID=<uuid> uv run pytest tests/e2e/` → 24+ passed, 0 failed
- End-to-end smoke test from Worker URL succeeds
- `git tag session-8-done`

---

## Dependency Graph

```
Session 1 (models + schema graph)
    └── Session 2 (retrieval layer)
            └── Session 3 (generation layer)
                    └── Session 4 (execution layer)
                            └── Session 5 (LangGraph pipeline)
                                    └── Session 6 (FastAPI app)
                                            ├── Session 7 (debug UI + worker)
                                            └── Session 8 (Vercel + E2E)
```

Sessions 7 and 8 both depend on Session 6 but are independent of each other. Run them in either order.

---

## How to Resume a Session

At the start of any session, a Claude instance should:
1. Read this file (`sessions.md`)
2. Read the main plan (`2026-06-01-text-sql-v2.md`) — specifically the tasks for this session
3. Read `DB_SCHEMA.md` for schema context
4. Read `CLAUDE.md` for project conventions
5. Check `git log --oneline -10` to confirm prior session tags are present
6. Run `uv run pytest` to confirm current passing state before adding new code
