import pytest
from core.generation_layer.clause_builder import SQLClauseBuilder
from core.models.intent import (
    QueryIntentJSON, QueryMetadata, StructuralPlan,
    FilterCondition, Aggregation, Ordering,
)

SCHEMA = {
    "tables": {
        "students": {"columns": [], "has_soft_delete": False, "has_school_id": True},
        "staff": {"columns": [], "has_soft_delete": True, "has_school_id": True},
        "classes": {"columns": [], "has_soft_delete": False, "has_school_id": True},
    },
    "foreign_keys": [],
}

def make_intent(tables, filters=None, aggregations=None, ordering=None, select_cols=None, joins=None):
    return QueryIntentJSON(
        query_metadata=QueryMetadata(raw_query="test", primary_domain="test", operational_intent="FILTERED_LIST", confidence=0.8),
        structural_plan=StructuralPlan(
            tables=tables,
            join_conditions=joins or [],
            select_columns=select_cols or [f"{tables[0]}.*"],
        ),
        filters=filters or [],
        aggregations=aggregations or [],
        ordering=ordering or [],
    )

def test_simple_select():
    builder = SQLClauseBuilder(SCHEMA)
    intent = make_intent(["students"])
    result = builder.build(intent, limit=10)
    assert "SELECT" in result.sql
    assert "FROM students" in result.sql
    assert "LIMIT 10" in result.sql

def test_soft_delete_filter_appended():
    builder = SQLClauseBuilder(SCHEMA)
    intent = make_intent(["staff"])
    result = builder.build(intent, limit=50)
    assert "staff.deleted_at IS NULL" in result.sql

def test_soft_delete_not_appended_for_non_soft_delete_table():
    builder = SQLClauseBuilder(SCHEMA)
    intent = make_intent(["students"])
    result = builder.build(intent, limit=10)
    assert "deleted_at" not in result.sql

def test_filter_condition_quoted():
    builder = SQLClauseBuilder(SCHEMA)
    intent = make_intent(
        ["students"],
        filters=[FilterCondition(table="students", column="full_name", operator="=", value="John", value_type="string")]
    )
    result = builder.build(intent, limit=10)
    assert "students.full_name = 'John'" in result.sql

def test_aggregation_count():
    builder = SQLClauseBuilder(SCHEMA)
    intent = make_intent(
        ["students"],
        select_cols=["COUNT(students.id)"],
        aggregations=[Aggregation(table="students", column="id", function="COUNT")],
    )
    result = builder.build(intent, limit=10)
    assert "COUNT(" in result.sql

def test_join_uses_left_join():
    builder = SQLClauseBuilder(SCHEMA)
    intent = make_intent(
        ["students", "classes"],
        joins=["students.class_section_id = classes.id"],
        select_cols=["students.*", "classes.name"],
    )
    result = builder.build(intent, limit=10)
    assert "LEFT JOIN" in result.sql
    assert "JOIN" in result.sql

def test_no_inner_join_used():
    import re as _re
    builder = SQLClauseBuilder(SCHEMA)
    intent = make_intent(
        ["students", "classes"],
        joins=["students.class_section_id = classes.id"],
        select_cols=["students.*", "classes.name"],
    )
    result = builder.build(intent, limit=10)
    sql_upper = result.sql.upper()
    assert "INNER JOIN" not in sql_upper
    # Every JOIN must be part of a LEFT JOIN — no bare JOIN allowed
    assert not _re.search(r'(?<!LEFT )JOIN', sql_upper)

def test_ordering():
    builder = SQLClauseBuilder(SCHEMA)
    intent = make_intent(
        ["students"],
        ordering=[Ordering(table="students", column="full_name", direction="ASC")],
    )
    result = builder.build(intent, limit=10)
    assert "ORDER BY students.full_name ASC" in result.sql

def test_no_sql_injection_in_string_value():
    builder = SQLClauseBuilder(SCHEMA)
    intent = make_intent(
        ["students"],
        filters=[FilterCondition(table="students", column="full_name", operator="=", value="'; DROP TABLE students; --", value_type="string")]
    )
    result = builder.build(intent, limit=10)
    # The value is wrapped in quotes and the inner quote is escaped as ''
    # so the injection cannot break out of the string literal
    assert "''" in result.sql  # the injected single quote is escaped as ''
    # The SQL must start with SELECT — no DML injected at the statement level
    assert result.sql.strip().upper().startswith("SELECT")

def test_sql_starts_with_select():
    builder = SQLClauseBuilder(SCHEMA)
    intent = make_intent(["students"])
    result = builder.build(intent, limit=10)
    assert result.sql.strip().upper().startswith("SELECT")

def test_numeric_injection_rejected():
    builder = SQLClauseBuilder(SCHEMA)
    intent = make_intent(
        ["students"],
        filters=[FilterCondition(table="students", column="grade", operator="=", value="5; DROP TABLE students; --", value_type="int")]
    )
    result = builder.build(intent, limit=10)
    assert "DROP TABLE" not in result.sql
    assert len(result.warnings) > 0  # non-numeric value should warn

def test_disallowed_operator_skipped():
    builder = SQLClauseBuilder(SCHEMA)
    intent = make_intent(
        ["students"],
        filters=[FilterCondition(table="students", column="grade", operator="= 1; DELETE FROM students; --", value="5", value_type="int")]
    )
    result = builder.build(intent, limit=10)
    assert "DELETE" not in result.sql
    assert len(result.warnings) > 0

def test_ordering_direction_allowlisted():
    builder = SQLClauseBuilder(SCHEMA)
    intent = make_intent(
        ["students"],
        ordering=[Ordering(table="students", column="full_name", direction="ASC; DROP TABLE students")]
    )
    result = builder.build(intent, limit=10)
    assert "DROP TABLE" not in result.sql

def test_no_wildcard_in_group_by():
    builder = SQLClauseBuilder(SCHEMA)
    intent = make_intent(
        ["students"],
        select_cols=["students.*", "COUNT(students.id)"],
        aggregations=[Aggregation(table="students", column="id", function="COUNT")],
    )
    result = builder.build(intent, limit=10)
    assert "GROUP BY students.*" not in result.sql


# ---------------------------------------------------------------------------
# OutputValidator tests
# ---------------------------------------------------------------------------
from core.generation_layer.output_validator import OutputValidator
from core.models.sql import SQLResult

def make_result(sql, confidence=0.8):
    return SQLResult(sql=sql, confidence_score=confidence, warnings=[], value_extractions={})

def test_valid_select_passes():
    v = OutputValidator()
    report = v.validate(make_result("SELECT students.* FROM students WHERE students.school_id = 'x' LIMIT 10"))
    assert report["is_valid"] is True

def test_no_select_fails():
    v = OutputValidator()
    report = v.validate(make_result("UPDATE students SET full_name='x'"))
    assert report["is_valid"] is False
    assert any("SELECT" in w for w in report["warnings"])

def test_no_from_fails():
    v = OutputValidator()
    report = v.validate(make_result("SELECT 1"))
    assert report["is_valid"] is False

def test_no_limit_fails():
    v = OutputValidator()
    report = v.validate(make_result("SELECT * FROM students"))
    assert report["is_valid"] is False
    assert any("LIMIT" in w for w in report["warnings"])

def test_semicolon_injection_fails():
    v = OutputValidator()
    report = v.validate(make_result("SELECT * FROM students; DROP TABLE students"))
    assert report["is_valid"] is False

def test_low_confidence_adds_warning():
    v = OutputValidator()
    report = v.validate(make_result("SELECT * FROM students LIMIT 10", confidence=0.3))
    assert any("confidence" in w.lower() for w in report["warnings"])
    # Rule 7 is non-blocking — low confidence does not make is_valid False
    assert report["is_valid"] is True

def test_comment_dash_injection_fails():
    v = OutputValidator()
    report = v.validate(make_result("SELECT * FROM students -- WHERE school_id=2\nLIMIT 10"))
    assert report["is_valid"] is False
    assert any("comment" in w.lower() for w in report["warnings"])

def test_comment_block_injection_fails():
    v = OutputValidator()
    report = v.validate(make_result("SELECT * FROM students /* ignore */ LIMIT 10"))
    assert report["is_valid"] is False

def test_forbidden_keyword_in_from_table_fails():
    v = OutputValidator()
    # Rule 5 in isolation — this SQL starts with SELECT and has LIMIT
    # but contains a forbidden keyword token outside a string literal
    report = v.validate(make_result("SELECT id FROM students UNION SELECT id FROM staff LIMIT 10"))
    assert report["is_valid"] is False
    assert any("union" in w.lower() or "Rule 5" in w for w in report["warnings"])


# ---------------------------------------------------------------------------
# ValueExtractor + SQLGenerator tests
# ---------------------------------------------------------------------------
from unittest.mock import MagicMock, patch
from core.generation_layer.value_extractor import ValueExtractor
from core.generation_layer.sql_generator import SQLGenerator

def test_value_extractor_fills_empty_values():
    with patch("litellm.completion") as mock_llm:
        mock_llm.return_value.choices = [MagicMock(message=MagicMock(content='{"values": {"students.full_name": "John Smith"}}'))]
        extractor = ValueExtractor()
        filters = [FilterCondition(table="students", column="full_name", operator="=", value="", value_type="string")]
        filled = extractor.fill_values(filters, "find student named John Smith")
        assert any(f.value == "John Smith" for f in filled)

def test_value_extractor_skips_llm_when_no_empty_filters():
    with patch("litellm.completion") as mock_llm:
        extractor = ValueExtractor()
        filters = [FilterCondition(table="students", column="full_name", operator="=", value="Alice", value_type="string")]
        result = extractor.fill_values(filters, "find student named Alice")
        mock_llm.assert_not_called()
        assert result[0].value == "Alice"

def test_value_extractor_returns_filters_on_llm_error():
    with patch("litellm.completion", side_effect=Exception("network error")):
        extractor = ValueExtractor()
        filters = [FilterCondition(table="students", column="full_name", operator="=", value="", value_type="string")]
        result = extractor.fill_values(filters, "find a student")
        assert result[0].value == ""  # unchanged — graceful fallback

def test_sql_generator_returns_sql_result():
    intent = make_intent(["students"])
    gen = SQLGenerator(SCHEMA)
    result = gen.generate(intent, limit=10)
    assert result.sql != ""
    assert "SELECT" in result.sql

def test_sql_generator_propagates_validation_warnings():
    bad_intent = make_intent(
        ["students"],
        filters=[FilterCondition(table="students", column="full_name", operator="=", value="'; DROP TABLE students; --", value_type="string")]
    )
    gen = SQLGenerator(SCHEMA)
    result = gen.generate(bad_intent, limit=10)
    # Injection is contained inside a quoted string literal — SQL still starts with SELECT
    # The validator catches semicolons and marks confidence 0.0
    assert result.sql.strip().upper().startswith("SELECT")
    assert result.confidence_score == 0.0  # validator invalidates due to semicolons/comments
