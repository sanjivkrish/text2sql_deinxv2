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

def test_school_id_injection_adds_where():
    runner = SQLRunner.__new__(SQLRunner)
    sql = "SELECT * FROM students LIMIT 10"
    injected = runner._inject_school_id(sql, "uuid-school-1", "students")
    assert "school_id = 'uuid-school-1'" in injected

def test_school_id_injection_appends_to_existing_where():
    runner = SQLRunner.__new__(SQLRunner)
    sql = "SELECT * FROM students WHERE students.full_name = 'John' LIMIT 10"
    injected = runner._inject_school_id(sql, "uuid-school-1", "students")
    assert "students.school_id = 'uuid-school-1'" in injected
    assert "full_name = 'John'" in injected

def test_school_id_injection_before_limit():
    runner = SQLRunner.__new__(SQLRunner)
    sql = "SELECT * FROM students LIMIT 10"
    injected = runner._inject_school_id(sql, "uuid-school-1", "students")
    limit_pos = injected.upper().find("LIMIT")
    school_pos = injected.find("school_id")
    assert school_pos < limit_pos
