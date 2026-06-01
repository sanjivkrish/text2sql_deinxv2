import pytest
from unittest.mock import MagicMock
from core.schema_layer.extractor import SchemaExtractor

MOCK_TABLES = [("students",), ("schools",), ("staff",)]
MOCK_COLUMNS = {
    "students": [("id", "uuid", False), ("school_id", "uuid", False), ("full_name", "text", False)],
    "schools": [("id", "uuid", False), ("name", "text", False)],
    "staff": [("id", "uuid", False), ("school_id", "uuid", False), ("first_name", "text", False), ("deleted_at", "timestamp with time zone", True)],
}
MOCK_FKS = [
    ("students", "school_id", "schools", "id"),
    ("staff", "school_id", "schools", "id"),
]

def make_mock_conn(tables, columns_map, fks):
    cursor = MagicMock()
    cursor.fetchall.side_effect = [
        tables,
        *[columns_map[t[0]] for t in tables],
        fks,
    ]
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = lambda s: cursor
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn, cursor

def test_extractor_returns_tables():
    conn, _ = make_mock_conn(MOCK_TABLES, MOCK_COLUMNS, MOCK_FKS)
    extractor = SchemaExtractor(conn)
    schema = extractor.extract()
    assert "students" in schema["tables"]
    assert "schools" in schema["tables"]

def test_extractor_columns_shape():
    conn, _ = make_mock_conn(MOCK_TABLES, MOCK_COLUMNS, MOCK_FKS)
    extractor = SchemaExtractor(conn)
    schema = extractor.extract()
    cols = schema["tables"]["students"]["columns"]
    assert any(c["name"] == "school_id" for c in cols)

def test_extractor_captures_fks():
    conn, _ = make_mock_conn(MOCK_TABLES, MOCK_COLUMNS, MOCK_FKS)
    extractor = SchemaExtractor(conn)
    schema = extractor.extract()
    fks = schema["foreign_keys"]
    assert any(f["from_table"] == "students" and f["to_table"] == "schools" for f in fks)

def test_extractor_flags_soft_delete_tables():
    conn, _ = make_mock_conn(MOCK_TABLES, MOCK_COLUMNS, MOCK_FKS)
    extractor = SchemaExtractor(conn)
    schema = extractor.extract()
    assert schema["tables"]["staff"]["has_soft_delete"] is True
    assert schema["tables"]["students"]["has_soft_delete"] is False
