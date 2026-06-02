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
