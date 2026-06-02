import re
import time
import psycopg
import psycopg.rows
from core.models.sql import SQLResult
from core.models.result import QueryRunResult

FORBIDDEN = {"insert", "update", "delete", "drop", "truncate", "alter", "create", "grant", "revoke"}


def _strip_quoted_literals(sql: str) -> str:
    return re.sub(r"'[^']*'", "''", sql)


class SQLRunner:
    def __init__(self, db_url: str):
        self._db_url = db_url

    def _safety_check(self, sql: str) -> None:
        stripped = _strip_quoted_literals(sql)
        tokens = set(re.findall(r'\b\w+\b', stripped.lower()))
        bad = tokens & FORBIDDEN
        if bad:
            raise ValueError(f"SQL failed safety check — forbidden tokens: {bad}")

    def _inject_school_id(self, sql: str, school_id: str, primary_table: str) -> str:
        condition = f"{primary_table}.school_id = '{school_id}'"
        if re.search(r'\bWHERE\b', sql, flags=re.IGNORECASE):
            sql = re.sub(
                r'(WHERE\s+)(.*?)((?:\s+(?:GROUP BY|ORDER BY|LIMIT))|$)',
                lambda m: m.group(1) + m.group(2) + f"\n  AND {condition}" + m.group(3),
                sql, flags=re.IGNORECASE | re.DOTALL
            )
        else:
            sql = re.sub(
                r'(LIMIT\s+\d+)',
                f'WHERE {condition}\n\\1',
                sql, flags=re.IGNORECASE
            )
        return sql

    def run(self, result: SQLResult, school_id: str, primary_table: str) -> QueryRunResult:
        self._safety_check(result.sql)
        scoped_sql = self._inject_school_id(result.sql, school_id, primary_table)
        start = time.monotonic()
        with psycopg.connect(self._db_url) as conn:
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
