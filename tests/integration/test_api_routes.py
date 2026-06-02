import json
import importlib
import os
import pytest
from fastapi.testclient import TestClient


MOCK_SCHOOL_ID = "a0000000-0000-0000-0000-000000000001"

TEST_SECRET = "test-secret"


def build_schema_file(tmp_path) -> str:
    """Build a small test schema_index.json identical to test_pipeline.py pattern."""
    from core.schema_layer.graph_builder import GraphBuilder
    from core.schema_layer.graph_store import GraphStore

    schema = {
        "tables": {
            "schools": {
                "columns": [{"name": "id", "type": "uuid", "nullable": False}],
                "has_soft_delete": False,
                "has_school_id": False,
            },
            "students": {
                "columns": [
                    {"name": "id", "type": "uuid", "nullable": False},
                    {"name": "school_id", "type": "uuid", "nullable": False},
                    {"name": "full_name", "type": "text", "nullable": True},
                ],
                "has_soft_delete": False,
                "has_school_id": True,
            },
        },
        "foreign_keys": [
            {
                "from_table": "students",
                "from_column": "school_id",
                "to_table": "schools",
                "to_column": "id",
            }
        ],
    }
    g = GraphBuilder(schema).build()
    path = str(tmp_path / "schema_index.json")
    GraphStore(path).save(g, schema)
    return path


@pytest.fixture()
def client(tmp_path):
    """
    Build test schema, set env vars, reload all api modules to clear
    module-level singletons, then yield a TestClient with lifespan running.
    """
    schema_path = build_schema_file(tmp_path)

    os.environ["SCHEMA_PATH"] = schema_path
    os.environ["DB_URL"] = "postgresql://mock"
    os.environ["INTERNAL_SECRET"] = TEST_SECRET

    # Reload route modules to reset module-level globals (_store, _pipeline etc.)
    import core.api.routes.health as health_mod
    import core.api.routes.schema as schema_mod
    import core.api.routes.query as query_mod
    import core.api.main as main_mod

    importlib.reload(health_mod)
    importlib.reload(schema_mod)
    importlib.reload(query_mod)
    importlib.reload(main_mod)

    # TestClient as context manager triggers lifespan (startup/shutdown)
    with TestClient(main_mod.app, headers={"X-Internal-Token": TEST_SECRET}) as c:
        yield c


def test_health_endpoint(client):
    """GET /health → 200, status ok (no token required)."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "graph_loaded" in data
    assert "db_reachable" in data
    assert "uptime_s" in data
    # DB is mock so db_reachable is False, but graph should be loaded
    assert data["graph_loaded"] is True


def test_schema_tables_endpoint(client):
    """GET /schema/tables → 200, "students" in response."""
    resp = client.get("/schema/tables")
    assert resp.status_code == 200
    data = resp.json()
    assert "students" in data
    assert "schools" in data
    # students table should have full_name column
    assert "full_name" in data["students"]


def test_unauthorized_without_token(tmp_path):
    """POST /query without token → 401."""
    schema_path = build_schema_file(tmp_path)
    os.environ["SCHEMA_PATH"] = schema_path
    os.environ["DB_URL"] = "postgresql://mock"
    os.environ["INTERNAL_SECRET"] = TEST_SECRET

    import core.api.routes.health as health_mod
    import core.api.routes.schema as schema_mod
    import core.api.routes.query as query_mod
    import core.api.main as main_mod

    importlib.reload(health_mod)
    importlib.reload(schema_mod)
    importlib.reload(query_mod)
    importlib.reload(main_mod)

    # Use TestClient WITHOUT auth header
    with TestClient(main_mod.app) as c:
        resp = c.post(
            "/query",
            json={"query": "list all students", "school_id": MOCK_SCHOOL_ID, "limit": 10},
        )
    assert resp.status_code == 401


def test_query_plan_endpoint(client):
    """POST /query/plan → 200, has 'query_plan' and 'intent' keys."""
    resp = client.post(
        "/query/plan",
        json={"query": "list all students", "school_id": MOCK_SCHOOL_ID, "limit": 10},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "query_plan" in data
    assert "intent" in data


def test_metrics_endpoint(client):
    """GET /metrics → 200, has 'requests_total' key (requires token)."""
    resp = client.get("/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert "requests_total" in data
    assert "requests_success" in data
    assert "requests_error" in data
    assert "avg_latency_ms" in data
    assert "rule_engine_hit_rate" in data
