import pytest
from unittest.mock import MagicMock, patch
from rag.interceptor import RAGInterceptor
from rag.models import MatchResult, FAQEntry
from core.models.sql import SQLResult
from core.models.result import QueryRunResult, TokenUsage


def _make_entry(**kwargs):
    defaults = dict(
        id="student-count-total",
        question="how many students are enrolled",
        alt_questions=[],
        sql="SELECT COUNT(*) AS total\nFROM students\nLIMIT 100",
        primary_table="students",
        intent="AGGREGATION",
        domain="student_management",
        has_variables=False,
    )
    defaults.update(kwargs)
    return FAQEntry(**defaults)


def _make_run_result():
    return QueryRunResult(rows=[{"total": 42}], row_count=1, execution_time_ms=5.0, sql="SELECT COUNT(*) AS total\nFROM students\nWHERE students.school_id = 'uuid'\nLIMIT 100")


def _make_usage():
    return TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150, estimated_cost_usd=0.0001)


@pytest.fixture
def interceptor(tmp_path):
    """RAGInterceptor with mocked retriever, runner, and summarizer."""
    runner = MagicMock()
    runner.run.return_value = _make_run_result()
    summarizer = MagicMock()
    summarizer.summarize.return_value = ("There are 42 students.", _make_usage())

    with patch("rag.interceptor.RAGRetriever") as mock_retriever_cls:
        mock_retriever = MagicMock()
        mock_retriever_cls.return_value = mock_retriever
        rag = RAGInterceptor(runner=runner, summarizer=summarizer)
        rag._retriever = mock_retriever
        rag._mock_runner = runner
        rag._mock_summarizer = summarizer
        yield rag, mock_retriever


def test_direct_tier_bypasses_pipeline(interceptor):
    rag, mock_retriever = interceptor
    entry = _make_entry()
    mock_retriever.search.return_value = MatchResult(
        tier="DIRECT", entry=entry, score=1.0, top_k=[]
    )
    pipeline = MagicMock()

    state = rag.intercept("how many students", "test-uuid", 100, pipeline)

    pipeline.invoke.assert_not_called()
    assert state.get("sql_result") is not None
    assert state.get("run_result") is not None
    assert state.get("summary") == "There are 42 students."
    assert state.get("error") is None


def test_direct_tier_substitutes_limit(interceptor):
    rag, mock_retriever = interceptor
    entry = _make_entry(sql="SELECT COUNT(*) AS total\nFROM students\nLIMIT 100")
    mock_retriever.search.return_value = MatchResult(
        tier="DIRECT", entry=entry, score=1.0, top_k=[]
    )
    pipeline = MagicMock()

    rag.intercept("how many students", "test-uuid", 25, pipeline)

    called_sql_result = rag._mock_runner.run.call_args[0][0]
    assert "LIMIT 25" in called_sql_result.sql
    assert "LIMIT 100" not in called_sql_result.sql


def test_few_shot_tier_calls_pipeline_with_examples(interceptor):
    rag, mock_retriever = interceptor
    entry = _make_entry()
    mock_retriever.search.return_value = MatchResult(
        tier="FEW_SHOT", entry=entry, score=0.75, top_k=[entry]
    )
    pipeline = MagicMock()
    pipeline.invoke.return_value = {"summary": "ok", "token_usage": _make_usage()}

    state = rag.intercept("how many students enrolled", "test-uuid", 100, pipeline)

    pipeline.invoke.assert_called_once()
    call_kwargs = pipeline.invoke.call_args[0][0]
    assert "few_shot_examples" in call_kwargs
    assert len(call_kwargs["few_shot_examples"]) >= 1
    assert call_kwargs["few_shot_examples"][0]["intent"] == "AGGREGATION"


def test_miss_tier_calls_pipeline_without_examples(interceptor):
    rag, mock_retriever = interceptor
    mock_retriever.search.return_value = MatchResult(
        tier="MISS", entry=None, score=0.0, top_k=[]
    )
    pipeline = MagicMock()
    pipeline.invoke.return_value = {"summary": "no result", "token_usage": _make_usage()}

    state = rag.intercept("gibberish unrelated", "test-uuid", 100, pipeline)

    pipeline.invoke.assert_called_once()
    call_kwargs = pipeline.invoke.call_args[0][0]
    assert "few_shot_examples" not in call_kwargs


def test_direct_tier_raises_on_runner_error(interceptor):
    rag, mock_retriever = interceptor
    entry = _make_entry()
    mock_retriever.search.return_value = MatchResult(
        tier="DIRECT", entry=entry, score=1.0, top_k=[]
    )
    rag._mock_runner.run.side_effect = Exception("DB connection failed")
    pipeline = MagicMock()

    with pytest.raises(Exception, match="DB connection failed"):
        rag.intercept("how many students", "test-uuid", 100, pipeline)
