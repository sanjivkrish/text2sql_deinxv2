import re
import json
from core.models.intent import (
    QueryIntentJSON, QueryMetadata, StructuralPlan,
    FilterCondition, Aggregation, Ordering,
)
from core.models.query import QueryPlan

INTENT_RULES: list[tuple[list[str], str]] = [
    (["how many", "count", "total number", "number of"], "AGGREGATION"),
    (["which.*most", "which.*highest", "which.*largest", "rank", "top \\d"], "COMPARATIVE"),
    (["this year", "academic year", "joined.*year", "current year", "this session"], "TEMPORAL"),
    (["roll number", "registration number", "employee id", "find.*with id", "specific student"], "POINT_LOOKUP"),
]
FILTERED_LIST_KEYWORDS = ["all", "list", "show", "display", "active", "inactive", "filter"]

def _detect_domain(query: str, plan: QueryPlan) -> str:
    tables = plan.recommended_tables
    if "students" in tables:
        return "student_management"
    if "staff" in tables:
        return "staff_management"
    if "admission_applications" in tables:
        return "admissions"
    if "classes" in tables or "subjects" in tables:
        return "academics"
    return "general"

def _rule_classify(query: str) -> tuple[str, float] | None:
    q = query.lower()
    for patterns, intent in INTENT_RULES:
        for p in patterns:
            if re.search(p, q):
                return intent, 0.85
    if any(kw in q for kw in FILTERED_LIST_KEYWORDS):
        return "FILTERED_LIST", 0.80
    return None

def _llm_classify(query: str, plan: QueryPlan) -> QueryIntentJSON:
    """LiteLLM fallback — structured output via JSON mode."""
    import litellm, os
    prompt = f"""Classify this school ERP query into one of: POINT_LOOKUP, FILTERED_LIST, AGGREGATION, COMPARATIVE, TEMPORAL.
Query: {query}
Tables likely involved: {plan.recommended_tables}
Return JSON: {{"intent": "...", "primary_domain": "...", "tables": [...], "filters": [], "aggregations": [], "ordering": []}}"""
    resp = litellm.completion(
        model=os.environ.get("LLM_MODEL", "claude-sonnet-4-6"),
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    data = json.loads(resp.choices[0].message.content)
    intent_str = data.get("intent", "FILTERED_LIST")
    tables = data.get("tables", plan.recommended_tables)
    return QueryIntentJSON(
        query_metadata=QueryMetadata(
            raw_query=query,
            primary_domain=data.get("primary_domain", "general"),
            operational_intent=intent_str,
            confidence=0.70,
        ),
        structural_plan=StructuralPlan(
            tables=tables,
            join_conditions=plan.recommended_joins,
            select_columns=[f"{t}.*" for t in tables[:1]],
        ),
        filters=[],
        aggregations=[],
        ordering=[],
    )

class IntentClassifier:
    def classify(self, query: str, plan: QueryPlan) -> QueryIntentJSON:
        rule_result = _rule_classify(query)
        if rule_result:
            intent_str, confidence = rule_result
        else:
            return _llm_classify(query, plan)

        tables = plan.recommended_tables or ["students"]
        return QueryIntentJSON(
            query_metadata=QueryMetadata(
                raw_query=query,
                primary_domain=_detect_domain(query, plan),
                operational_intent=intent_str,
                confidence=confidence,
            ),
            structural_plan=StructuralPlan(
                tables=tables,
                join_conditions=plan.recommended_joins,
                select_columns=[f"{tables[0]}.*"] if tables else ["*"],
            ),
            filters=[],
            aggregations=[],
            ordering=[],
        )
