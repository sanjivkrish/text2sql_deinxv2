import json
import pytest
from pathlib import Path
from rag.indexer import tokenize, build_index
from rag.models import FAQIndex


def test_tokenize_basic():
    tokens = tokenize("how many students are enrolled")
    assert "many" in tokens
    assert "students" in tokens
    assert "enrolled" in tokens
    # stopwords removed
    assert "how" not in tokens
    assert "the" not in tokens


def test_tokenize_lowercases():
    tokens = tokenize("List ALL Students")
    assert "list" in tokens
    assert "all" in tokens
    assert "students" in tokens
    assert "List" not in tokens


def test_tokenize_removes_short_tokens():
    tokens = tokenize("show a b students")
    assert "a" not in tokens
    assert "b" not in tokens
    assert "students" in tokens


_MINIMAL_JSONL = """\
{"id": "s-count", "question": "how many students", "alt_questions": ["total students"], "sql": "SELECT COUNT(*) AS total\\nFROM students\\nLIMIT 100", "primary_table": "students", "intent": "AGGREGATION", "domain": "student_management", "has_variables": false}
{"id": "s-list", "question": "list all students", "alt_questions": [], "sql": "SELECT students.full_name\\nFROM students\\nORDER BY students.full_name ASC\\nLIMIT 100", "primary_table": "students", "intent": "FILTERED_LIST", "domain": "student_management", "has_variables": false}
"""


def test_build_index_produces_valid_faqindex(tmp_path):
    src = tmp_path / "faq.jsonl"
    src.write_text(_MINIMAL_JSONL)
    dst = tmp_path / "faq_index.json"
    build_index(str(src), str(dst))
    assert dst.exists()
    data = json.loads(dst.read_text())
    idx = FAQIndex(**data)
    assert idx.version == 1
    assert len(idx.entries) == 2
    # corpus: 2 questions + 1 alt = 3 docs
    assert len(idx.corpus) == 3
    assert idx.max_self_score > 0


def test_build_index_rejects_dml(tmp_path):
    src = tmp_path / "bad.jsonl"
    src.write_text(
        '{"id": "x", "question": "q", "alt_questions": [], "sql": "DELETE FROM students", '
        '"primary_table": "students", "intent": "AGGREGATION", "domain": "x", "has_variables": false}\n'
    )
    dst = tmp_path / "out.json"
    with pytest.raises(ValueError, match="forbidden"):
        build_index(str(src), str(dst))


def test_build_index_deduplicates_corpus_entry_ids(tmp_path):
    src = tmp_path / "faq.jsonl"
    # entry with 2 alts → 3 corpus docs, all same entry_id
    src.write_text(
        '{"id": "e1", "question": "total students", "alt_questions": ["student count", "how many students"], '
        '"sql": "SELECT COUNT(*) AS total\\nFROM students\\nLIMIT 100", "primary_table": "students", '
        '"intent": "AGGREGATION", "domain": "student_management", "has_variables": false}\n'
    )
    dst = tmp_path / "out.json"
    build_index(str(src), str(dst))
    data = json.loads(dst.read_text())
    idx = FAQIndex(**data)
    assert len(idx.corpus) == 3
    assert all(d["entry_id"] == "e1" for d in data["corpus"])


def test_build_index_rejects_empty_corpus(tmp_path):
    src = tmp_path / "faq.jsonl"
    src.write_text(
        '{"id": "x", "question": "the a an", "alt_questions": ["of for"], '
        '"sql": "SELECT 1\\nFROM students\\nLIMIT 100", "primary_table": "students", '
        '"intent": "AGGREGATION", "domain": "x", "has_variables": false}\n'
    )
    dst = tmp_path / "out.json"
    with pytest.raises(ValueError):
        build_index(str(src), str(dst))
