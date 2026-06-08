import psycopg

# Tables excluded from the schema graph — internal/auth tables the LLM should never reference
_EXCLUDED_TABLES = {
    "profiles",
    "school_admin_credentials_mvp",
    "school_memberships",
    "role_feature_permissions",
    "feature_catalog",
    "school_feature_settings",
    "parent_form_tokens",
    "staff_audit_log",
    "staff_employee_id_sequence",
}

_TABLES_SQL = """
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
    ORDER BY table_name
"""

_COLUMNS_SQL = """
    SELECT column_name, data_type, is_nullable = 'YES'
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = %s
    ORDER BY ordinal_position
"""

_FKS_SQL = """
    SELECT
        kcu.table_name AS from_table,
        kcu.column_name AS from_column,
        ccu.table_name AS to_table,
        ccu.column_name AS to_column
    FROM information_schema.table_constraints AS tc
    JOIN information_schema.key_column_usage AS kcu
        ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
    JOIN information_schema.constraint_column_usage AS ccu
        ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema
    WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'
    ORDER BY kcu.table_name, kcu.column_name
"""


class SchemaExtractor:
    def __init__(self, conn):
        self._conn = conn

    def extract(self) -> dict:
        tables: dict[str, dict] = {}
        with self._conn.cursor() as cur:
            cur.execute(_TABLES_SQL, prepare=False)
            table_rows = cur.fetchall()

            for (table_name,) in table_rows:
                if table_name in _EXCLUDED_TABLES:
                    continue
                cur.execute(_COLUMNS_SQL, (table_name,), prepare=False)
                col_rows = cur.fetchall()
                columns = [
                    {"name": name, "type": dtype, "nullable": nullable}
                    for name, dtype, nullable in col_rows
                ]
                col_names = {c["name"] for c in columns}
                tables[table_name] = {
                    "columns": columns,
                    "has_soft_delete": "deleted_at" in col_names,
                    "has_school_id": "school_id" in col_names,
                }

            cur.execute(_FKS_SQL, prepare=False)
            fk_rows = cur.fetchall()

        foreign_keys = [
            {"from_table": ft, "from_column": fc, "to_table": tt, "to_column": tc}
            for ft, fc, tt, tc in fk_rows
            if ft not in _EXCLUDED_TABLES and tt not in _EXCLUDED_TABLES
        ]

        return {"tables": tables, "foreign_keys": foreign_keys}
