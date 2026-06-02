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

def _llm_classify(query: str, plan: QueryPlan, intent_hint: tuple[str, float] | None = None) -> QueryIntentJSON:
    """LLM classification with optional rule-based intent hint."""
    import litellm, os
    from core.schema_layer.graph_store import GraphStore
    VALID_INTENTS = {"POINT_LOOKUP", "FILTERED_LIST", "AGGREGATION", "COMPARATIVE", "TEMPORAL"}

    # Build schema hint: recommended tables + their FK-related child tables (1 hop)
    schema_hint = ""
    available_joins: list[str] = []
    try:
        store = GraphStore(os.environ.get("SCHEMA_PATH", "db/schema_index.json"))
        _, schema = store.load()
        all_tables = schema.get("tables", {})
        fks = schema.get("foreign_keys", [])

        # Expand to include child tables that FK into any recommended table
        base_tables = [t for t in plan.recommended_tables if t in all_tables]
        related: list[str] = list(base_tables)
        for fk in fks:
            if fk["to_table"] in base_tables and fk["from_table"] not in related and fk["from_table"] in all_tables:
                related.append(fk["from_table"])

        # Collect FK join conditions for all related tables (so LLM can pick them)
        joined_in_hint: set[str] = set(base_tables)
        for fk in fks:
            if fk["from_table"] in related and fk["to_table"] in related:
                jc = f"{fk['from_table']}.{fk['from_column']} = {fk['to_table']}.{fk['to_column']}"
                if jc not in available_joins:
                    available_joins.append(jc)
                joined_in_hint.add(fk["from_table"])
                joined_in_hint.add(fk["to_table"])

        lines = []
        for t in related[:6]:  # cap to avoid bloating the prompt
            cols = [c["name"] for c in all_tables[t]["columns"]]
            lines.append(f"  {t}: {cols}")
        schema_hint = "Available columns:\n" + "\n".join(lines) + "\n\n"
    except Exception:
        pass

    joins_hint = ""
    if available_joins:
        joins_hint = "Available JOIN conditions (use exactly as written):\n" + "\n".join(f"  {j}" for j in available_joins) + "\n\n"

    from datetime import date
    today = date.today().isoformat()

    hint_line = ""
    if intent_hint:
        hint_line = f"Hint: rule pre-classifier detected intent '{intent_hint[0]}' (confidence {intent_hint[1]}). Use this as a strong prior.\n"

    prompt = f"""You are classifying a school ERP natural-language query.

Today's date: {today}
Query: "{query}"
Tables likely involved: {plan.recommended_tables}
{hint_line}{schema_hint}{joins_hint}Intent types:
- POINT_LOOKUP: query about a specific named person or record (e.g. "find student Amudha", "details about teacher Ravi")
- FILTERED_LIST: list filtered by one or more conditions (e.g. "all active students in grade 5")
- AGGREGATION: count, sum, or average (e.g. "how many students", "total staff")
- COMPARATIVE: ranking or comparison (e.g. "which class has the most students")
- TEMPORAL: time-based query (e.g. "students enrolled this year")

Rules:
- Use ONLY column names from the schema above — never invent column names.
- If the query involves certifications/qualifications/experience, use the dedicated sub-table (e.g. staff_certifications, staff_qualifications) — NOT a column on the parent table.
- For POINT_LOOKUP: always include a filter on the person's name column using ILIKE with %name% pattern.
- For FILTERED_LIST: include filters for any explicit conditions mentioned.
- filters must have: table, column (exact name from schema), operator (=, ILIKE, >, <, etc.), value, value_type (string/int/bool/date/expression).
- For categorical string columns (gender, status, designation, employment_type, staff_category, etc.): use operator "ILIKE" with the lowercase value (e.g. value "male", not "Male") for case-insensitive exact matching.
- For age filters on dob columns: larger age = earlier date.
  "above age N" / "older than N" → operator "<", value "CURRENT_DATE - INTERVAL 'N years'", value_type "expression"
  "below age N" / "younger than N" → operator ">", value "CURRENT_DATE - INTERVAL 'N years'", value_type "expression"
- For AGGREGATION intent: populate "aggregations" with the COUNT/SUM/AVG to compute.
  aggregations: [{{"table": "...", "column": "*", "function": "COUNT", "alias": "total"}}]
  Always include matching filters (e.g. gender ILIKE 'male') alongside the aggregation.
- For ordering: populate "ordering" with column and direction (ASC/DESC).
- join_conditions: include all JOIN conditions needed (use exactly the strings from "Available JOIN conditions" above).

Return valid JSON only:
{{
  "intent": "...",
  "primary_domain": "...",
  "tables": ["..."],
  "join_conditions": ["..."],
  "filters": [{{"table": "...", "column": "...", "operator": "=", "value": "...", "value_type": "string"}}],
  "aggregations": [{{"table": "...", "column": "*", "function": "COUNT", "alias": "total"}}],
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

    # Use LLM-provided join_conditions if present; fall back to planner's
    llm_joins = data.get("join_conditions") or []
    join_conditions = [str(j) for j in llm_joins if j] or plan.recommended_joins

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

    # SELECT: primary table.* + any columns from joined tables that appear in filters
    primary = tables[0] if tables else "students"
    extra_cols: list[str] = []
    seen: set[str] = set()
    for f in filters:
        if f.table != primary:
            ref = f"{f.table}.{f.column}"
            if ref not in seen:
                extra_cols.append(ref)
                seen.add(ref)
    select_columns = [f"{primary}.*"] + extra_cols

    raw_aggs = data.get("aggregations") or []
    aggregations: list[Aggregation] = []
    for a in raw_aggs:
        try:
            aggregations.append(Aggregation(
                table=a["table"],
                column=a["column"],
                function=a["function"],
                alias=a.get("alias", ""),
            ))
        except (KeyError, TypeError):
            continue

    raw_ordering = data.get("ordering") or []
    ordering: list[Ordering] = []
    for o in raw_ordering:
        try:
            ordering.append(Ordering(
                table=o["table"],
                column=o["column"],
                direction=o.get("direction", "ASC"),
            ))
        except (KeyError, TypeError):
            continue

    confidence = intent_hint[1] if intent_hint else 0.70

    return QueryIntentJSON(
        query_metadata=QueryMetadata(
            raw_query=query,
            primary_domain=data.get("primary_domain", "general"),
            operational_intent=intent_str,
            confidence=confidence,
        ),
        structural_plan=StructuralPlan(
            tables=tables,
            join_conditions=join_conditions,
            select_columns=select_columns,
        ),
        filters=filters,
        aggregations=aggregations,
        ordering=ordering,
    )

class IntentClassifier:
    def classify(self, query: str, plan: QueryPlan) -> QueryIntentJSON:
        # Always use LLM for full detail extraction (filters, aggregations, ordering).
        # Rule pre-classifier provides a high-confidence hint to bias the LLM.
        rule_result = _rule_classify(query)
        return _llm_classify(query, plan, intent_hint=rule_result)

