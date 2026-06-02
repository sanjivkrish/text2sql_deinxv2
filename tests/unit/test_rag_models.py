import pytest
from rag.models import FAQEntry, MatchResult, CorpusDoc, FAQIndex


def _entry(**kwargs):
    defaults = dict(
        id="test-entry",
        question="how many students",
        alt_questions=["student count"],
        sql="SELECT COUNT(*) AS total\nFROM students\nLIMIT 100",
        primary_table="students",
        intent="AGGREGATION",
        domain="student_management",
        has_variables=False,
    )
    defaults.update(kwargs)
    return FAQEntry(**defaults)


def test_faq_entry_defaults():
    e = _entry()
    assert e.has_variables is False
    assert e.intent == "AGGREGATION"


def test_faq_entry_has_variables_true():
    e = _entry(has_variables=True)
    assert e.has_variables is True


def test_match_result_miss():
    r = MatchResult(tier="MISS", entry=None, score=0.0, top_k=[])
    assert r.tier == "MISS"
    assert r.entry is None
    assert r.top_k == []


def test_match_result_direct():
    e = _entry()
    r = MatchResult(tier="DIRECT", entry=e, score=0.92, top_k=[])
    assert r.tier == "DIRECT"
    assert r.score == 0.92


def test_faq_index_structure():
    e = _entry()
    doc = CorpusDoc(tokens=["how", "many", "students"], entry_id="test-entry")
    idx = FAQIndex(
        version=1,
        built_at="2026-06-02T00:00:00",
        entries=[e],
        corpus=[doc],
        max_self_score=3.5,
    )
    assert idx.version == 1
    assert len(idx.corpus) == 1
    assert idx.max_self_score == 3.5
