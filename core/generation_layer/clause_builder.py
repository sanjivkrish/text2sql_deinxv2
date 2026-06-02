import re
from core.models.intent import QueryIntentJSON, FilterCondition
from core.models.sql import SQLResult

def _quote_string(value: str) -> str:
    """Escape single quotes to prevent SQL injection."""
    return "'" + value.replace("'", "''") + "'"

class SQLClauseBuilder:
    def __init__(self, schema: dict):
        self._schema = schema

    def build(self, intent: QueryIntentJSON, limit: int = 100) -> SQLResult:
        warnings: list[str] = []
        sp = intent.structural_plan
        tables = sp.tables
        if not tables:
            return SQLResult(sql="", confidence_score=0.0, warnings=["No tables resolved"], value_extractions={})

        primary_table = tables[0]

        # SELECT clause
        select_parts = sp.select_columns if sp.select_columns else [f"{primary_table}.*"]
        # Inject aggregations into select_parts
        for agg in intent.aggregations:
            agg_col = f"{agg.function}({agg.table}.{agg.column})"
            if agg_col not in select_parts and f"{agg.table}.*" in select_parts:
                select_parts = [agg_col if s == f"{agg.table}.*" else s for s in select_parts]

        select_clause = "SELECT " + ", ".join(select_parts)

        # FROM + LEFT JOINs — always LEFT JOIN to preserve left-side rows
        from_clause = f"FROM {primary_table}"
        for i, join_sql in enumerate(sp.join_conditions):
            parts = re.split(r"\s*=\s*", join_sql)
            if len(parts) == 2:
                right_tbl = parts[1].split(".")[0]
                if i + 1 < len(tables) and tables[i + 1] != primary_table:
                    right_tbl = tables[i + 1]
                from_clause += f"\nLEFT JOIN {right_tbl} ON {join_sql}"

        # WHERE clause
        where_parts: list[str] = []
        for f in intent.filters:
            if f.value_type in ("string", "text", "name"):
                val = _quote_string(f.value)
            elif f.value_type in ("int", "integer", "number"):
                val = f.value
            elif f.value_type == "bool":
                val = f.value.lower()
            else:
                val = _quote_string(f.value)
            where_parts.append(f"{f.table}.{f.column} {f.operator} {val}")

        # Soft-delete guard for tables that have deleted_at
        for t in tables:
            if t in self._schema["tables"] and self._schema["tables"][t]["has_soft_delete"]:
                where_parts.append(f"{t}.deleted_at IS NULL")

        where_clause = ("WHERE " + "\n  AND ".join(where_parts)) if where_parts else ""

        # GROUP BY — if aggregations present, group by all non-aggregate columns
        group_parts = [
            col for col in select_parts
            if not any(agg.function in col for agg in intent.aggregations)
        ]
        group_clause = ("GROUP BY " + ", ".join(group_parts)) if intent.aggregations and group_parts else ""

        # ORDER BY
        order_parts = [f"{o.table}.{o.column} {o.direction}" for o in intent.ordering]
        order_clause = ("ORDER BY " + ", ".join(order_parts)) if order_parts else ""

        # Assemble — always read-only SELECT
        parts = [select_clause, from_clause]
        if where_clause:
            parts.append(where_clause)
        if group_clause:
            parts.append(group_clause)
        if order_clause:
            parts.append(order_clause)
        parts.append(f"LIMIT {limit}")

        sql = "\n".join(parts)
        confidence = 0.85 if intent.query_metadata.confidence >= 0.75 else 0.70
        return SQLResult(sql=sql, confidence_score=confidence, warnings=warnings, value_extractions={})
