import re
from core.models.intent import QueryIntentJSON, FilterCondition
from core.models.sql import SQLResult

def _quote_string(value: str) -> str:
    """Escape single quotes to prevent SQL injection."""
    return "'" + value.replace("'", "''") + "'"

# Fix 2: allowlisted operators
_ALLOWED_OPERATORS = {"=", "!=", "<>", "<", ">", "<=", ">=", "LIKE", "ILIKE", "IN", "IS NULL", "IS NOT NULL"}

# Fix 5: allowlisted ORDER BY directions
_ALLOWED_DIRECTIONS = {"ASC", "DESC"}

# Fix 6: identifier validation regex
_IDENT_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')

def _safe_ident(name: str) -> str:
    """Raise ValueError if name is not a safe SQL identifier."""
    if not _IDENT_RE.match(name):
        raise ValueError(f"Unsafe SQL identifier: {name!r}")
    return name


class SQLClauseBuilder:
    def __init__(self, schema: dict):
        self._schema = schema

    def build(self, intent: QueryIntentJSON, limit: int = 100) -> SQLResult:
        warnings: list[str] = []
        sp = intent.structural_plan
        tables = sp.tables
        if not tables:
            return SQLResult(sql="", confidence_score=0.0, warnings=["No tables resolved"], value_extractions={})

        # Prefer a primary table that participates in at least one join condition.
        # This avoids an orphaned FROM table when the planner/LLM returns an
        # unrelated table first (e.g. academic_years before students).
        join_table_mentions: set[str] = set()
        for jc in sp.join_conditions:
            jc_sides = re.split(r"\s*=\s*", jc, maxsplit=1)
            if len(jc_sides) == 2:
                join_table_mentions.add(jc_sides[0].strip().split(".")[0])
                join_table_mentions.add(jc_sides[1].strip().split(".")[0])

        raw_primary = tables[0]
        if join_table_mentions and raw_primary not in join_table_mentions:
            for t in tables:
                if t in join_table_mentions:
                    raw_primary = t
                    break

        try:
            primary_table = _safe_ident(raw_primary)
        except ValueError as e:
            return SQLResult(sql="", confidence_score=0.0, warnings=[str(e)], value_extractions={})

        # SELECT clause — re-anchor a single wildcard to the resolved primary table
        # so SELECT doesn't reference a table that was never added to the FROM chain.
        # For pure aggregation queries drop any raw column selections — they would
        # bleed into GROUP BY and produce invalid "GROUP BY table.id" on a COUNT(*).
        is_pure_agg = bool(intent.aggregations) and not intent.ordering
        if is_pure_agg:
            select_parts = []
        else:
            select_parts = sp.select_columns if sp.select_columns else [f"{primary_table}.*"]
            if len(select_parts) == 1 and select_parts[0].endswith(".*"):
                select_parts = [f"{primary_table}.*"]

        # Fix 3: inject aggregations — replace wildcard if present, otherwise prepend
        for agg in intent.aggregations:
            try:
                _safe_ident(agg.table)
                if agg.column != "*":
                    _safe_ident(agg.column)
            except ValueError as e:
                warnings.append(str(e))
                continue
            # COUNT(*) is standard; COUNT(table.*) is invalid SQL
            agg_col = f"{agg.function}(*)" if agg.column == "*" else f"{agg.function}({agg.table}.{agg.column})"
            if agg_col not in select_parts:
                if f"{agg.table}.*" in select_parts:
                    select_parts = [agg_col if s == f"{agg.table}.*" else s for s in select_parts]
                else:
                    select_parts = [agg_col] + [s for s in select_parts]

        select_clause = "SELECT " + ", ".join(select_parts)

        # FROM + LEFT JOINs — derive join table from condition, not from tables index
        from_clause = f"FROM {primary_table}"
        joined_tables: set[str] = {primary_table}
        for join_sql in sp.join_conditions:
            parts = re.split(r"\s*=\s*", join_sql, maxsplit=1)
            if len(parts) != 2:
                continue
            left_tbl = parts[0].strip().split(".")[0]
            right_tbl = parts[1].strip().split(".")[0]
            left_in = left_tbl in joined_tables
            right_in = right_tbl in joined_tables
            if left_in and right_in:
                continue  # both already in chain, skip duplicate
            elif left_in:
                join_tbl = right_tbl
            elif right_in:
                join_tbl = left_tbl
            else:
                # Neither side connected to the FROM chain — skip to avoid broken SQL
                warnings.append(f"Skipped unconnected join: {join_sql!r}")
                continue
            try:
                join_tbl = _safe_ident(join_tbl)
            except ValueError as e:
                warnings.append(str(e))
                continue
            from_clause += f"\nLEFT JOIN {join_tbl} ON {join_sql}"
            joined_tables.add(join_tbl)

        # WHERE clause
        where_parts: list[str] = []
        for f in intent.filters:
            # Fix 6: sanitize table and column identifiers
            try:
                _safe_ident(f.table)
                _safe_ident(f.column)
            except ValueError as e:
                warnings.append(str(e))
                continue

            # validate and format filter value by type
            if f.value_type in ("string", "text", "name"):
                val = _quote_string(f.value)
            elif f.value_type in ("int", "integer", "number"):
                if not re.fullmatch(r"-?\d+(\.\d+)?", f.value.strip()):
                    warnings.append(f"Non-numeric value rejected (invalid): {f.table}.{f.column}")
                    continue
                else:
                    val = f.value.strip()
            elif f.value_type == "bool":
                if f.value.strip().lower() not in ("true", "false"):
                    warnings.append(f"Non-boolean value rejected (invalid): {f.table}.{f.column}")
                    continue
                else:
                    val = f.value.strip().lower()
            elif f.value_type == "date":
                # ISO date literal — quote as string, PostgreSQL casts automatically
                val = _quote_string(f.value.strip())
            elif f.value_type == "expression":
                # Safe SQL expressions: only allow CURRENT_DATE arithmetic and intervals
                raw = f.value.strip()
                if not re.fullmatch(
                    r"CURRENT_DATE(\s*[-+]\s*INTERVAL\s*'\d+\s+\w+')?",
                    raw, re.IGNORECASE
                ):
                    warnings.append(f"Unsafe expression rejected for {f.table}.{f.column}: {raw!r}")
                    continue
                val = raw
            else:
                val = _quote_string(f.value)

            # Fix 2: allowlist the operator
            op = f.operator.strip().upper()
            if op not in _ALLOWED_OPERATORS:
                warnings.append(f"Disallowed operator '{f.operator}' skipped for {f.table}.{f.column}")
                continue

            where_parts.append(f"{f.table}.{f.column} {op} {val}")

        # Soft-delete guard for tables that have deleted_at
        for t in tables:
            # Fix 6: sanitize soft-delete table identifier
            try:
                safe_t = _safe_ident(t)
            except ValueError as e:
                warnings.append(str(e))
                continue
            if safe_t in self._schema["tables"] and self._schema["tables"][safe_t]["has_soft_delete"]:
                where_parts.append(f"{safe_t}.deleted_at IS NULL")

        where_clause = ("WHERE " + "\n  AND ".join(where_parts)) if where_parts else ""

        # Fix 4: GROUP BY — exclude both aggregate expressions AND wildcards
        group_parts = [
            col for col in select_parts
            if not any(agg.function in col for agg in intent.aggregations)
            and "*" not in col  # wildcards are invalid in GROUP BY
        ]
        group_clause = ("GROUP BY " + ", ".join(group_parts)) if intent.aggregations and group_parts else ""

        # Fix 5: ORDER BY with allowlisted direction
        order_parts = []
        for o in intent.ordering:
            # Fix 6: sanitize ordering identifiers
            try:
                _safe_ident(o.table)
                _safe_ident(o.column)
            except ValueError as e:
                warnings.append(str(e))
                continue
            direction = o.direction.strip().upper()
            if direction not in _ALLOWED_DIRECTIONS:
                warnings.append(f"Invalid ORDER direction '{o.direction}' replaced with ASC")
                direction = "ASC"
            order_parts.append(f"{o.table}.{o.column} {direction}")

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
