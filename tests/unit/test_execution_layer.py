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


# --- ResultSummarizer tests ---

from unittest.mock import MagicMock, patch
from core.execution_layer.summarizer import ResultSummarizer
from core.models.result import QueryRunResult, TokenUsage

SAMPLE_RUN = QueryRunResult(
    rows=[{"full_name": "Alice", "school_id": "uuid-1"}, {"full_name": "Bob", "school_id": "uuid-1"}],
    row_count=2,
    execution_time_ms=42.0,
    sql="SELECT * FROM students WHERE students.school_id = 'uuid-1'\nLIMIT 10",
)

def test_summarizer_returns_string_and_token_usage():
    with patch("litellm.completion") as mock_llm:
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = "There are 2 students."
        mock_resp.usage.prompt_tokens = 100
        mock_resp.usage.completion_tokens = 20
        mock_resp.usage.total_tokens = 120
        mock_llm.return_value = mock_resp
        summarizer = ResultSummarizer()
        summary, usage = summarizer.summarize("show all students", SAMPLE_RUN)
        assert "2" in summary or "students" in summary.lower()
        assert usage.total_tokens == 120

def test_summarizer_empty_rows():
    with patch("litellm.completion") as mock_llm:
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = "No students found."
        mock_resp.usage.prompt_tokens = 50
        mock_resp.usage.completion_tokens = 10
        mock_resp.usage.total_tokens = 60
        mock_llm.return_value = mock_resp
        summarizer = ResultSummarizer()
        run = QueryRunResult(rows=[], row_count=0, execution_time_ms=10.0, sql="SELECT *")
        summary, usage = summarizer.summarize("show students", run)
        assert isinstance(summary, str)
        assert usage.total_tokens > 0

def test_summarizer_handles_llm_error_gracefully():
    with patch("litellm.completion") as mock_llm:
        mock_llm.side_effect = Exception("Network error")
        summarizer = ResultSummarizer()
        run = QueryRunResult(rows=[], row_count=0, execution_time_ms=10.0, sql="SELECT *")
        summary, usage = summarizer.summarize("show students", run)
        assert isinstance(summary, str)
        assert usage.total_tokens == 0
