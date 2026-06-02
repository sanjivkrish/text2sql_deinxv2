import re
import time
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from core.models.result import QueryResponse, TokenUsage
from core.schema_layer.graph_store import GraphStore

router = APIRouter()
_pipeline = None
_store: GraphStore | None = None
_rag = None

# Destructive / adversarial tokens that have no place in a read-only NL query interface
_DESTRUCTIVE_TOKENS = frozenset({
    # SQL DDL/DML verbs
    "delete", "drop", "truncate", "insert", "alter", "create", "grant", "revoke",
    # Natural-language synonyms for removing data
    "displace", "purge", "wipe", "erase",
    # Security-bypass signals
    "bypass",
})
# Multi-word adversarial patterns
_ADVERSARIAL_RE = re.compile(
    r'\b(ignore|override|circumvent|disable)\b.{0,40}\b(rule|security|restriction|constraint|limit|check)'
    r'|do\s+not\s+(produce|show|raise|return)\s+(error|exception)'
    r'|suppress\s+(error|exception|check)',
    re.IGNORECASE,
)


def _has_destructive_intent(query: str) -> bool:
    tokens = set(re.findall(r'\b\w+\b', query.lower()))
    if tokens & _DESTRUCTIVE_TOKENS:
        return True
    if _ADVERSARIAL_RE.search(query):
        return True
    return False


def init(pipeline, store: GraphStore, runner=None, summarizer=None):
    global _pipeline, _store, _rag
    from rag.interceptor import RAGInterceptor
    _pipeline = pipeline
    _store = store
    if runner is not None and summarizer is not None:
        _rag = RAGInterceptor(runner=runner, summarizer=summarizer)


class QueryRequest(BaseModel):
    query: str
    school_id: str
    limit: int = 100


@router.post("/query", response_model=QueryResponse)
def run_query(req: QueryRequest):
    if _pipeline is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    if _has_destructive_intent(req.query):
        raise HTTPException(
            status_code=400,
            detail="Only read-only queries are supported. Queries with destructive or adversarial intent are rejected.",
        )
    from core.api.routes import health as health_routes
    t0 = time.monotonic()
    try:
        if _rag is not None:
            state = _rag.intercept(
                req.query, req.school_id, req.limit,
                _pipeline,
            )
        else:
            state = _pipeline.invoke({
                "query": req.query,
                "school_id": req.school_id,
                "limit": req.limit,
            })
    except Exception as e:
        total_ms = (time.monotonic() - t0) * 1000
        health_routes.record(success=False, latency_ms=total_ms)
        raise HTTPException(status_code=500, detail=str(e))

    total_ms = (time.monotonic() - t0) * 1000

    if state.get("error"):
        health_routes.record(success=False, latency_ms=total_ms)
        raise HTTPException(status_code=400, detail=state["error"])

    usage = state.get("token_usage") or TokenUsage(
        input_tokens=0, output_tokens=0, total_tokens=0, estimated_cost_usd=0.0
    )
    health_routes.record(
        success=True,
        latency_ms=total_ms,
        cost_usd=usage.estimated_cost_usd,
        rule_hit=True,
    )

    plan = state.get("query_plan")
    sql_result = state.get("sql_result")

    run_result = state.get("run_result")

    return QueryResponse(
        query=req.query,
        school_id=req.school_id,
        summary=state.get("summary", ""),
        token_usage=usage,
        confidence=plan.confidence if plan else 0.0,
        warnings=sql_result.warnings if sql_result else [],
        timing={"total_ms": total_ms},
        sql=run_result.sql if run_result else (sql_result.sql if sql_result else None),
    )


@router.post("/query/plan")
def query_plan(req: QueryRequest):
    """Dry-run: plan + classify only, no execution."""
    if _store is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    if _has_destructive_intent(req.query):
        raise HTTPException(
            status_code=400,
            detail="Only read-only queries are supported. Queries with destructive or adversarial intent are rejected.",
        )
    from core.retrieval_layer.semantic_mapper import SemanticMapper
    from core.retrieval_layer.traversal import TraversalEngine
    from core.retrieval_layer.query_planner import QueryGraphPlanner
    from core.retrieval_layer.intent_classifier import IntentClassifier
    g, schema = _store.graph, _store.schema
    mapper = SemanticMapper(g, schema)
    engine = TraversalEngine(g)
    planner = QueryGraphPlanner(mapper, engine, schema)
    classifier = IntentClassifier()
    plan = planner.plan(req.query)
    intent = classifier.classify(req.query, plan)
    return {"query_plan": plan.model_dump(), "intent": intent.model_dump()}
