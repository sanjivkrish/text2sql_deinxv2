import json
import pytest
from rag.indexer import build_index
from rag.retriever import RAGRetriever


_MINIMAL_JSONL = """\
{"id": "s-count", "question": "how many students are enrolled", "alt_questions": ["total student count", "number of students"], "sql": "SELECT COUNT(*) AS total\\nFROM students\\nLIMIT 100", "primary_table": "students", "intent": "AGGREGATION", "domain": "student_management", "has_variables": false}
{"id": "s-list", "question": "list all active students", "alt_questions": ["show active students"], "sql": "SELECT students.full_name\\nFROM students\\nWHERE students.status ILIKE 'active'\\nORDER BY students.full_name ASC\\nLIMIT 100", "primary_table": "students", "intent": "FILTERED_LIST", "domain": "student_management", "has_variables": false}
{"id": "s-lookup", "question": "find a student by name", "alt_questions": ["look up student by name"], "sql": "SELECT students.full_name\\nFROM students\\nWHERE students.full_name ILIKE '%placeholder%'\\nLIMIT 100", "primary_table": "students", "intent": "POINT_LOOKUP", "domain": "student_management", "has_variables": true}
"""


@pytest.fixture
def retriever(tmp_path):
    src = tmp_path / "faq.jsonl"
    src.write_text(_MINIMAL_JSONL)
    dst = tmp_path / "faq_index.json"
    build_index(str(src), str(dst))
    return RAGRetriever(str(dst))


def test_exact_match_is_direct(retriever):
    result = retriever.search("how many students are enrolled")
    assert result.tier == "DIRECT"
    assert result.entry.id == "s-count"
    assert result.score >= 0.85


def test_alt_question_match(retriever):
    result = retriever.search("total student count")
    assert result.tier in ("DIRECT", "FEW_SHOT")
    assert result.entry.id == "s-count"


def test_unrelated_query_is_miss(retriever):
    result = retriever.search("xyz qrst unrelated gibberish abcdef")
    assert result.tier == "MISS"
    assert result.entry is None
    assert result.score == 0.0


def test_has_variables_capped_at_few_shot(retriever):
    # "find a student by name" has has_variables=True — even at high score, must not be DIRECT
    result = retriever.search("find a student by name")
    assert result.tier != "DIRECT"


def test_few_shot_top_k_populated(retriever):
    result = retriever.search("list all active students")
    if result.tier == "FEW_SHOT":
        assert len(result.top_k) >= 1
        assert all(e.id for e in result.top_k)


def test_search_returns_match_result_type(retriever):
    from rag.models import MatchResult
    result = retriever.search("how many students")
    assert isinstance(result, MatchResult)
