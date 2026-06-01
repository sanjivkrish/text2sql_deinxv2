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


from core.schema_layer.graph_builder import GraphBuilder
import networkx as nx

SAMPLE_SCHEMA = {
    "tables": {
        "schools": {"columns": [{"name": "id", "type": "uuid", "nullable": False}], "has_soft_delete": False, "has_school_id": False},
        "students": {"columns": [{"name": "id", "type": "uuid", "nullable": False}, {"name": "school_id", "type": "uuid", "nullable": False}, {"name": "full_name", "type": "text", "nullable": True}], "has_soft_delete": False, "has_school_id": True},
        "staff": {"columns": [{"name": "id", "type": "uuid", "nullable": False}, {"name": "school_id", "type": "uuid", "nullable": False}, {"name": "deleted_at", "type": "timestamp with time zone", "nullable": True}], "has_soft_delete": True, "has_school_id": True},
    },
    "foreign_keys": [
        {"from_table": "students", "from_column": "school_id", "to_table": "schools", "to_column": "id"},
        {"from_table": "staff", "from_column": "school_id", "to_table": "schools", "to_column": "id"},
    ],
}

def test_graph_has_table_nodes():
    g = GraphBuilder(SAMPLE_SCHEMA).build()
    assert "tbl_schools" in g.nodes
    assert "tbl_students" in g.nodes

def test_graph_has_column_nodes():
    g = GraphBuilder(SAMPLE_SCHEMA).build()
    assert "col_students.full_name" in g.nodes
    assert "col_students.school_id" in g.nodes

def test_graph_fk_edge_has_join_sql():
    g = GraphBuilder(SAMPLE_SCHEMA).build()
    assert g.has_edge("tbl_students", "tbl_schools")
    edge = g["tbl_students"]["tbl_schools"]
    assert "students.school_id = schools.id" in edge["join_sql"]

def test_graph_soft_delete_flag():
    g = GraphBuilder(SAMPLE_SCHEMA).build()
    assert g.nodes["tbl_staff"]["has_soft_delete"] is True
    assert g.nodes["tbl_schools"]["has_soft_delete"] is False

import json, tempfile, os
from core.schema_layer.graph_store import GraphStore

def test_graph_store_save_and_load(tmp_path):
    g = GraphBuilder(SAMPLE_SCHEMA).build()
    path = str(tmp_path / "schema_index.json")
    store = GraphStore(path)
    store.save(g, SAMPLE_SCHEMA)
    loaded_g, loaded_schema = store.load()
    assert "tbl_students" in loaded_g.nodes
    assert "students" in loaded_schema["tables"]

def test_graph_store_singleton_returns_same_instance(tmp_path):
    g = GraphBuilder(SAMPLE_SCHEMA).build()
    path = str(tmp_path / "schema_index.json")
    store = GraphStore(path)
    store.save(g, SAMPLE_SCHEMA)
    store.load()
    g1 = store.graph
    store.load()
    g2 = store.graph
    assert g1 is g2
