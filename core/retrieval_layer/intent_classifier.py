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
    from core.schema_layer.graph_store import GraphStore
    VALID_INTENTS = {"POINT_LOOKUP", "FILTERED_LIST", "AGGREGATION", "COMPARATIVE", "TEMPORAL"}

    # Build a compact table→columns reference so the LLM uses real column names
    schema_hint = ""
    try:
        store = GraphStore(os.environ.get("SCHEMA_PATH", "db/schema_index.json"))
        _, schema = store.load()
        relevant = [t for t in plan.recommended_tables if t in schema.get("tables", {})]
        lines = []
        for t in relevant[:4]:  # cap to avoid bloating the prompt
            cols = [c["name"] for c in schema["tables"][t]["columns"]]
            lines.append(f"  {t}: {cols}")
        schema_hint = "Available columns:\n" + "\n".join(lines) + "\n\n"
    except Exception:
        pass

    prompt = f"""You are classifying a school ERP natural-language query.

Query: "{query}"
Tables likely involved: {plan.recommended_tables}
{schema_hint}Intent types:
- POINT_LOOKUP: query about a specific named person or record (e.g. "find student Amudha", "details about teacher Ravi")
- FILTERED_LIST: list filtered by one or more conditions (e.g. "all active students in grade 5")
- AGGREGATION: count, sum, or average (e.g. "how many students", "total staff")
- COMPARATIVE: ranking or comparison (e.g. "which class has the most students")
- TEMPORAL: time-based query (e.g. "students enrolled this year")

Rules:
- For POINT_LOOKUP: always include a filter on the person's name column (use the exact column name from the schema above) using ILIKE with %name% pattern.
- For FILTERED_LIST: include filters for any explicit conditions mentioned.
- filters must have: table, column (must be an exact column name from the schema), operator (=, ILIKE, >, <, etc.), value, value_type (string/int/bool).

Return valid JSON only:
{{
  "intent": "...",
  "primary_domain": "...",
  "tables": ["..."],
  "filters": [{{"table": "...", "column": "...", "operator": "ILIKE", "value": "%...%", "value_type": "string"}}],
  "aggregations": [],
  "ordering": []
}}"""
    resp = litellm.completion(
        model=os.environ.get("LLM_MODEL", "claude-sonnet-4-6"),
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content
    try:
        data = json.loads(content) if content else {}
    except (json.JSONDecodeError, TypeError):
        data = {}
    intent_str = data.get("intent", "FILTERED_LIST")
    if intent_str not in VALID_INTENTS:
        intent_str = "FILTERED_LIST"
    tables = data.get("tables", plan.recommended_tables) or plan.recommended_tables

    raw_filters = data.get("filters") or []
    filters: list[FilterCondition] = []
    for f in raw_filters:
        try:
            filters.append(FilterCondition(
                table=f["table"],
                column=f["column"],
                operator=f["operator"],
                value=str(f.get("value", "")),
                value_type=f.get("value_type", "string"),
            ))
        except (KeyError, TypeError):
            continue

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
        filters=filters,
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
