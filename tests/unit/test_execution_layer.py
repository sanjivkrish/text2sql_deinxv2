import pytest
from unittest.mock import MagicMock, patch
from core.execution_layer.runner import SQLRunner
from core.models.sql import SQLResult

def make_result(sql):
    return SQLResult(sql=sql, confidence_score=0.9, warnings=[], value_extractions={})

def test_safety_gate_blocks_update():
    runner = SQLRunner.__new__(SQLRunner)
    with pytest.raises(ValueError, match="safety"):
        runner._safety_check("UPDATE students SET name='x'")

def test_safety_gate_allows_select():
    runner = SQLRunner.__new__(SQLRunner)
    runner._safety_check("SELECT * FROM students LIMIT 10")  # no exception

def test_safety_gate_not_fooled_by_update_in_string():
    runner = SQLRunner.__new__(SQLRunner)
    runner._safety_check("SELECT * FROM students WHERE full_name = 'UPDATE something' LIMIT 10")

_VALID_UUID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

def test_school_id_injection_adds_where():
    runner = SQLRunner.__new__(SQLRunner)
    sql = "SELECT * FROM students\nLIMIT 10"
    injected = runner._inject_school_id(sql, _VALID_UUID, "students")
    assert f"school_id = '{_VALID_UUID}'" in injected

def test_school_id_injection_appends_to_existing_where():
    runner = SQLRunner.__new__(SQLRunner)
    sql = "SELECT * FROM students WHERE students.full_name = 'John'\nLIMIT 10"
    injected = runner._inject_school_id(sql, _VALID_UUID, "students")
    assert f"students.school_id = '{_VALID_UUID}'" in injected
    assert "full_name = 'John'" in injected

def test_school_id_injection_before_limit():
    runner = SQLRunner.__new__(SQLRunner)
    sql = "SELECT * FROM students\nLIMIT 10"
    injected = runner._inject_school_id(sql, _VALID_UUID, "students")
    limit_pos = injected.upper().find("LIMIT")
    school_pos = injected.find("school_id")
    assert school_pos < limit_pos


def test_safety_gate_handles_unterminated_literal():
    runner = SQLRunner.__new__(SQLRunner)
    # Unterminated literal containing DROP — should be caught
    with pytest.raises(ValueError, match="safety"):
        runner._safety_check("SELECT * FROM students WHERE name = 'foo DROP TABLE students")


def test_school_id_injection_rejects_invalid_uuid():
    runner = SQLRunner.__new__(SQLRunner)
    sql = "SELECT * FROM students\nLIMIT 10"
    with pytest.raises(ValueError, match="school_id"):
        runner._inject_school_id(sql, "not-a-uuid", "students")
