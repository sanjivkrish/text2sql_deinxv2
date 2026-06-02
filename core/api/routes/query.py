import time
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from core.models.result import QueryResponse, TokenUsage
from core.schema_layer.graph_store import GraphStore

router = APIRouter()
_pipeline = None
_store: GraphStore | None = None


def init(pipeline, store: GraphStore):
    global _pipeline, _store
    _pipeline = pipeline
    _store = store


class QueryRequest(BaseModel):
    query: str
    school_id: str
    limit: int = 100


@router.post("/query", response_model=QueryResponse)
def run_query(req: QueryRequest):
    if _pipeline is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    from core.api.routes import health as health_routes
    t0 = time.monotonic()
    try:
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

    return QueryResponse(
        query=req.query,
        school_id=req.school_id,
        summary=state.get("summary", ""),
        token_usage=usage,
        confidence=plan.confidence if plan else 0.0,
        warnings=sql_result.warnings if sql_result else [],
        timing={"total_ms": total_ms},
    )


@router.post("/query/plan")
def query_plan(req: QueryRequest):
    """Dry-run: plan + classify only, no execution."""
    if _store is None:
        raise HTTPException(status_code=503, detail="Service not ready")
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
