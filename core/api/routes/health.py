import time
import threading
from collections import deque
from fastapi import APIRouter
from core.schema_layer.graph_store import GraphStore

router = APIRouter()
_start_time = time.time()
_store: GraphStore | None = None
_db_url: str = ""

_lock = threading.Lock()
_metrics = {
    "requests_total": 0,
    "requests_success": 0,
    "requests_error": 0,
    "latencies_ms": deque(maxlen=1000),
    "token_costs": deque(maxlen=1000),
    "rule_hits": 0,
    "llm_fallbacks": 0,
}


def init(store: GraphStore, db_url: str):
    global _store, _db_url
    _store = store
    _db_url = db_url


@router.get("/health")
def health():
    graph_loaded = _store is not None and _store.graph is not None
    db_ok = False
    try:
        import psycopg
        with psycopg.connect(_db_url, connect_timeout=2) as conn:
            conn.execute("SELECT 1")
        db_ok = True
    except Exception:
        pass
    return {
        "status": "ok",
        "graph_loaded": graph_loaded,
        "db_reachable": db_ok,
        "uptime_s": int(time.time() - _start_time),
    }


@router.get("/metrics")
def metrics():
    with _lock:
        total = _metrics["requests_total"]
        lats = list(_metrics["latencies_ms"])
        costs = list(_metrics["token_costs"])
        rule_hits = _metrics["rule_hits"]
        return {
            "requests_total": total,
            "requests_success": _metrics["requests_success"],
            "requests_error": _metrics["requests_error"],
            "avg_latency_ms": (sum(lats) / len(lats)) if lats else 0,
            "avg_token_cost_usd": (sum(costs) / len(costs)) if costs else 0,
            "rule_engine_hit_rate": (rule_hits / total) if total else 0,
            "llm_fallback_rate": (_metrics["llm_fallbacks"] / total) if total else 0,
        }


def record(success: bool, latency_ms: float, cost_usd: float = 0, rule_hit: bool = True):
    with _lock:
        _metrics["requests_total"] += 1
        if success:
            _metrics["requests_success"] += 1
        else:
            _metrics["requests_error"] += 1
        _metrics["latencies_ms"].append(latency_ms)
        if cost_usd:
            _metrics["token_costs"].append(cost_usd)
        if rule_hit:
            _metrics["rule_hits"] += 1
        else:
            _metrics["llm_fallbacks"] += 1
