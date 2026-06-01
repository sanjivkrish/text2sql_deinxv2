from core.models import (
    QueryPlan, ResolvedEntity, TraversalResult,
    QueryIntentJSON, QueryMetadata, StructuralPlan,
    SQLResult, QueryResponse, TokenUsage,
)

def test_query_plan_roundtrip():
    plan = QueryPlan(
        resolved_entities=[ResolvedEntity(raw_text="students", table="students", column=None, confidence=0.9)],
        join_paths=[TraversalResult(path=["tbl_students"], join_sql=[], hop_count=0)],
        recommended_tables=["students"],
        recommended_joins=[],
        confidence=0.9,
    )
    assert plan.model_dump()["confidence"] == 0.9

def test_query_response_no_rows():
    resp = QueryResponse(
        query="test",
        school_id="abc-uuid",
        summary="summary",
        token_usage=TokenUsage(input_tokens=10, output_tokens=5, total_tokens=15, estimated_cost_usd=0.001),
        confidence=0.8,
        warnings=[],
        timing={"total_ms": 200.0},
    )
    assert "rows" not in resp.model_fields  # raw rows not in QueryResponse
