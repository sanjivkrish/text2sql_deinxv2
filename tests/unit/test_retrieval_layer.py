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


# ---------------------------------------------------------------------------
# QueryGraphPlanner tests
# ---------------------------------------------------------------------------
from core.retrieval_layer.query_planner import QueryGraphPlanner

@pytest.fixture
def planner():
    g = GraphBuilder(TRAVERSAL_SCHEMA).build()
    mapper = SemanticMapper(g, TRAVERSAL_SCHEMA)
    engine = TraversalEngine(g)
    return QueryGraphPlanner(mapper, engine, TRAVERSAL_SCHEMA)

def test_planner_single_table_query(planner):
    plan = planner.plan("show all students")
    assert "students" in plan.recommended_tables
    assert plan.confidence > 0.5

def test_planner_multi_table_query(planner):
    plan = planner.plan("show students in each class")
    tables = set(plan.recommended_tables)
    assert "students" in tables
    assert "classes" in tables

def test_planner_plan_has_confidence(planner):
    plan = planner.plan("list all students")
    assert 0.0 < plan.confidence <= 1.0

def test_planner_discovers_join_path(planner):
    plan = planner.plan("students classes")
    tables = set(plan.recommended_tables)
    assert "students" in tables
    assert "classes" in tables
    assert len(plan.recommended_joins) > 0


# ---------------------------------------------------------------------------
# IntentClassifier tests
# ---------------------------------------------------------------------------
from unittest.mock import patch
from core.retrieval_layer.intent_classifier import IntentClassifier
from core.models.intent import QueryIntentJSON, QueryMetadata, StructuralPlan
from core.models.query import QueryPlan, ResolvedEntity, TraversalResult

EMPTY_PLAN = QueryPlan(resolved_entities=[], join_paths=[], recommended_tables=["students"], recommended_joins=[], confidence=0.8)

@pytest.fixture
def classifier():
    return IntentClassifier()

def test_aggregation_rule(classifier):
    intent = classifier.classify("how many students are in each class", EMPTY_PLAN)
    assert intent.query_metadata.operational_intent == "AGGREGATION"
    assert intent.query_metadata.confidence >= 0.75

def test_point_lookup_rule(classifier):
    intent = classifier.classify("find student with roll number 42", EMPTY_PLAN)
    assert intent.query_metadata.operational_intent == "POINT_LOOKUP"

def test_filtered_list_rule(classifier):
    intent = classifier.classify("show all active staff members", EMPTY_PLAN)
    assert intent.query_metadata.operational_intent == "FILTERED_LIST"

def test_temporal_rule(classifier):
    intent = classifier.classify("how many students joined this academic year", EMPTY_PLAN)
    assert intent.query_metadata.operational_intent in ("TEMPORAL", "AGGREGATION")

def test_comparative_rule(classifier):
    intent = classifier.classify("which class has the most students", EMPTY_PLAN)
    assert intent.query_metadata.operational_intent == "COMPARATIVE"

def test_intent_has_structural_plan(classifier):
    intent = classifier.classify("list all students", EMPTY_PLAN)
    assert isinstance(intent.structural_plan.tables, list)
    assert len(intent.structural_plan.tables) > 0

def test_llm_fallback_called_for_ambiguous_query(classifier):
    with patch("core.retrieval_layer.intent_classifier._llm_classify") as mock_llm:
        mock_llm.return_value = QueryIntentJSON(
            query_metadata=QueryMetadata(
                raw_query="who is the principal",
                primary_domain="staff_management",
                operational_intent="POINT_LOOKUP",
                confidence=0.70,
            ),
            structural_plan=StructuralPlan(tables=["staff"], join_conditions=[], select_columns=["staff.*"]),
            filters=[],
            aggregations=[],
            ordering=[],
        )
        plan = QueryPlan(resolved_entities=[], join_paths=[], recommended_tables=["staff"], recommended_joins=[], confidence=0.8)
        intent = classifier.classify("who is the principal", plan)
        mock_llm.assert_called_once()
        assert intent.query_metadata.operational_intent == "POINT_LOOKUP"
        assert intent.query_metadata.confidence == 0.70

def test_detect_domain_by_table(classifier):
    from core.retrieval_layer.intent_classifier import _detect_domain
    student_plan = QueryPlan(resolved_entities=[], join_paths=[], recommended_tables=["students"], recommended_joins=[], confidence=0.8)
    staff_plan = QueryPlan(resolved_entities=[], join_paths=[], recommended_tables=["staff"], recommended_joins=[], confidence=0.8)
    general_plan = QueryPlan(resolved_entities=[], join_paths=[], recommended_tables=["timetables"], recommended_joins=[], confidence=0.8)
    assert _detect_domain("q", student_plan) == "student_management"
    assert _detect_domain("q", staff_plan) == "staff_management"
    assert _detect_domain("q", general_plan) == "general"
