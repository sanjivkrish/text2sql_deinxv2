import pytest
import networkx as nx
from core.schema_layer.graph_builder import GraphBuilder
from core.retrieval_layer.semantic_mapper import SemanticMapper

SCHEMA = {
    "tables": {
        "schools": {"columns": [{"name": "id", "type": "uuid", "nullable": False}, {"name": "name", "type": "text", "nullable": False}], "has_soft_delete": False, "has_school_id": False},
        "students": {"columns": [{"name": "id", "type": "uuid", "nullable": False}, {"name": "school_id", "type": "uuid", "nullable": False}, {"name": "full_name", "type": "text", "nullable": True}, {"name": "class_section_id", "type": "uuid", "nullable": True}, {"name": "date_of_birth", "type": "date", "nullable": True}], "has_soft_delete": False, "has_school_id": True},
        "staff": {"columns": [{"name": "id", "type": "uuid", "nullable": False}, {"name": "school_id", "type": "uuid", "nullable": False}, {"name": "first_name", "type": "text", "nullable": False}, {"name": "designation", "type": "text", "nullable": True}, {"name": "deleted_at", "type": "timestamp with time zone", "nullable": True}], "has_soft_delete": True, "has_school_id": True},
        "classes": {"columns": [{"name": "id", "type": "uuid", "nullable": False}, {"name": "school_id", "type": "uuid", "nullable": False}, {"name": "name", "type": "text", "nullable": False}, {"name": "grade_level", "type": "smallint", "nullable": False}], "has_soft_delete": False, "has_school_id": True},
        "academic_years": {"columns": [{"name": "id", "type": "uuid", "nullable": False}, {"name": "school_id", "type": "uuid", "nullable": False}, {"name": "name", "type": "text", "nullable": False}, {"name": "is_current", "type": "boolean", "nullable": False}], "has_soft_delete": False, "has_school_id": True},
    },
    "foreign_keys": [
        {"from_table": "students", "from_column": "school_id", "to_table": "schools", "to_column": "id"},
        {"from_table": "staff", "from_column": "school_id", "to_table": "schools", "to_column": "id"},
        {"from_table": "classes", "from_column": "school_id", "to_table": "schools", "to_column": "id"},
        {"from_table": "academic_years", "from_column": "school_id", "to_table": "schools", "to_column": "id"},
    ],
}

@pytest.fixture
def mapper():
    g = GraphBuilder(SCHEMA).build()
    return SemanticMapper(g, SCHEMA)

def test_maps_student_token(mapper):
    results = mapper.map("students")
    tables = [r.table for r in results]
    assert "students" in tables

def test_maps_teacher_to_staff(mapper):
    results = mapper.map("teacher")
    tables = [r.table for r in results]
    assert "staff" in tables

def test_maps_class_token(mapper):
    results = mapper.map("class")
    tables = [r.table for r in results]
    assert "classes" in tables

def test_maps_academic_year(mapper):
    results = mapper.map("academic year")
    tables = [r.table for r in results]
    assert "academic_years" in tables

def test_maps_dob_column(mapper):
    results = mapper.map("date of birth")
    assert any(r.column == "date_of_birth" for r in results)

def test_confidence_range(mapper):
    results = mapper.map("students")
    assert all(0.0 <= r.confidence <= 1.0 for r in results)


# ---------------------------------------------------------------------------
# TraversalEngine tests
# ---------------------------------------------------------------------------
from core.retrieval_layer.traversal import TraversalEngine

TRAVERSAL_SCHEMA = {
    "tables": {
        "schools": {"columns": [{"name": "id", "type": "uuid", "nullable": False}], "has_soft_delete": False, "has_school_id": False},
        "classes": {"columns": [{"name": "id", "type": "uuid", "nullable": False}, {"name": "school_id", "type": "uuid", "nullable": False}], "has_soft_delete": False, "has_school_id": True},
        "class_sections": {"columns": [{"name": "id", "type": "uuid", "nullable": False}, {"name": "school_id", "type": "uuid", "nullable": False}, {"name": "class_id", "type": "uuid", "nullable": False}], "has_soft_delete": False, "has_school_id": True},
        "students": {"columns": [{"name": "id", "type": "uuid", "nullable": False}, {"name": "school_id", "type": "uuid", "nullable": False}, {"name": "class_section_id", "type": "uuid", "nullable": True}], "has_soft_delete": False, "has_school_id": True},
    },
    "foreign_keys": [
        {"from_table": "classes", "from_column": "school_id", "to_table": "schools", "to_column": "id"},
        {"from_table": "class_sections", "from_column": "school_id", "to_table": "schools", "to_column": "id"},
        {"from_table": "class_sections", "from_column": "class_id", "to_table": "classes", "to_column": "id"},
        {"from_table": "students", "from_column": "school_id", "to_table": "schools", "to_column": "id"},
        {"from_table": "students", "from_column": "class_section_id", "to_table": "class_sections", "to_column": "id"},
    ],
}

@pytest.fixture
def engine():
    g = GraphBuilder(TRAVERSAL_SCHEMA).build()
    return TraversalEngine(g)

def test_direct_fk_path(engine):
    result = engine.find_path("class_sections", "classes")
    assert result is not None
    assert result.hop_count == 1
    assert "class_sections.class_id = classes.id" in result.join_sql

def test_two_hop_path(engine):
    result = engine.find_path("students", "classes")
    assert result is not None
    assert result.hop_count == 2
    assert result.path == ["students", "class_sections", "classes"]
    assert len(result.join_sql) == 2
    assert "students.class_section_id = class_sections.id" in result.join_sql
    assert "class_sections.class_id = classes.id" in result.join_sql

def test_no_path_returns_none(engine):
    result = engine.find_path("students", "nonexistent_table")
    assert result is None

def test_same_table_returns_empty(engine):
    result = engine.find_path("students", "students")
    assert result is not None
    assert result.hop_count == 0
    assert result.join_sql == []

def test_no_fk_path_between_real_tables(engine):
    # All FKs in TRAVERSAL_SCHEMA point to 'schools' — no outgoing path from schools
    result = engine.find_path("schools", "students")
    assert result is None
