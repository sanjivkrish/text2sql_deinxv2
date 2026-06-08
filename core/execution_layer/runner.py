import re
import time
import psycopg
import psycopg.rows
from core.models.sql import SQLResult
from core.models.result import QueryRunResult

FORBIDDEN = {"insert", "update", "delete", "drop", "truncate", "alter", "create", "grant", "revoke"}

_UUID_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE
)

_IDENT_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')


def _strip_quoted_literals(sql: str) -> str:
    return re.sub(r"'[^']*'|'[^']*$", "''", sql)


class SQLRunner:
    def __init__(self, db_url: str):
        self._db_url = db_url

    def _safety_check(self, sql: str) -> None:
        # Detect unterminated string literals — treat as a safety violation
        if "'" in re.sub(r"'[^']*'", "", sql):
            raise ValueError("SQL failed safety check — unterminated string literal detected")
        stripped = _strip_quoted_literals(sql)
        tokens = set(re.findall(r'\b\w+\b', stripped.lower()))
        bad = tokens & FORBIDDEN
        if bad:
            raise ValueError(f"SQL failed safety check — forbidden tokens: {bad}")

    def _inject_school_id(self, sql: str, school_id: str, primary_table: str) -> str:
        if not _UUID_RE.match(school_id):
            raise ValueError(f"Invalid school_id format: {school_id!r}")
        if not _IDENT_RE.match(primary_table):
            raise ValueError(f"Unsafe table identifier: {primary_table!r}")
        condition = f"{primary_table}.school_id = '{school_id}'"

        # Clause builder always emits LIMIT as the last line ("\nLIMIT n")
        # Split body from limit for safe injection
        limit_match = re.search(r'(\n)(LIMIT\s+\d+\s*)$', sql, re.IGNORECASE)
        if limit_match:
            before_limit = sql[:limit_match.start()]
            sep = limit_match.group(1)
            limit_part = limit_match.group(2)
        else:
            before_limit = sql
            sep = "\n"
            limit_part = None

        if re.search(r'\bWHERE\b', before_limit, re.IGNORECASE):
            injected_body = before_limit + f"\n  AND {condition}"
        else:
            injected_body = before_limit + f"\nWHERE {condition}"

        if limit_part:
            return injected_body + sep + limit_part
        return injected_body

    def run(self, result: SQLResult, school_id: str, primary_table: str) -> QueryRunResult:
        self._safety_check(result.sql)
        scoped_sql = self._inject_school_id(result.sql, school_id, primary_table)
        start = time.monotonic()
        with psycopg.connect(self._db_url, prepare_threshold=0) as conn:
            with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                cur.execute(scoped_sql)
                rows = cur.fetchall()
        elapsed_ms = (time.monotonic() - start) * 1000
        return QueryRunResult(
            rows=rows,
            row_count=len(rows),
            execution_time_ms=elapsed_ms,
            sql=scoped_sql,
        )
