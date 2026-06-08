# RAG BM25 Cache — Design Spec

**Date:** 2026-06-02  
**Branch:** `rag-bm25-cache`  
**Status:** Approved for implementation

---

## Overview

A modular FAQ cache layer that intercepts natural-language queries before they reach the LLM pipeline. Pre-verified SQL answers for common queries are retrieved via BM25 similarity. High-confidence matches bypass the classifier and generator entirely (zero LLM tokens). Medium-confidence matches inject verified examples as few-shot context into the classifier prompt.

**Goal:** Reduce Groq token usage on the free tier (100K TPD) for common, repetitive school ERP queries, while improving SQL accuracy for near-match queries.

---

## Constraints

- All new code lives in `rag/`. Zero new files in `core/` until Phase 3 integration.
- The `rag/` module must not be imported by any `core/` file in Phases 1–2.
- SQL templates in `faq.jsonl` are school-agnostic — no `school_id` literals. The existing `SQLRunner._inject_school_id()` handles injection unchanged.
- Only read-only SELECT SQL in `faq.jsonl`. Any entry with DML is rejected at index build time.
- New dependency: `rank_bm25 >= 0.2` (pure Python, ~10 KB, no C extensions).

---

## Directory Layout

```
rag/
  __init__.py
  models.py          ← FAQEntry, FAQIndex, MatchResult (Pydantic)
  indexer.py         ← build_index(): faq.jsonl → faq_index.json
  retriever.py       ← RAGRetriever: BM25 search, 3-tier result
  interceptor.py     ← RAGInterceptor: wraps pipeline.invoke() (Phase 3)
  faq.jsonl          ← source of truth: hand-authored NLP → SQL pairs
  faq_index.json     ← built artifact: tokenized BM25 corpus (committed to git)

scripts/
  build_faq_index.py  ← CLI: uv run python scripts/build_faq_index.py
  test_faq_sql.py     ← CLI: runs each FAQ SQL against DB, reports pass/fail
```

---

## Data Model

### FAQEntry (`rag/models.py`)

```python
class FAQEntry(BaseModel):
    id: str                      # kebab-case slug, unique
    question: str                # primary canonical question
    alt_questions: list[str]     # alternate phrasings (same SQL)
    sql: str                     # school-agnostic SQL template (SELECT only), ends with LIMIT 100
    primary_table: str           # table name for SQLRunner.run() school_id injection
    intent: str                  # AGGREGATION | FILTERED_LIST | POINT_LOOKUP | COMPARATIVE | TEMPORAL
    domain: str                  # student_management | staff_management | academics | admissions
    has_variables: bool = False  # True if SQL uses placeholder values (e.g. class name, person name)
                                 # Entries with has_variables=True are capped at FEW_SHOT regardless
                                 # of BM25 score — they cannot be DIRECT-served.
```

### MatchResult (`rag/models.py`)

```python
class MatchResult(BaseModel):
    tier: Literal["DIRECT", "FEW_SHOT", "MISS"]
    entry: FAQEntry | None       # None when tier == MISS
    score: float                 # normalized BM25 score [0.0, 1.0]
    top_k: list[FAQEntry]        # top-3 entries (for FEW_SHOT few-shot examples)
```

### FAQIndex (`rag/models.py`)

```python
class CorpusDoc(BaseModel):
    tokens: list[str]
    entry_id: str

class FAQIndex(BaseModel):
    version: int
    built_at: str
    entries: list[FAQEntry]
    corpus: list[CorpusDoc]      # one doc per question+alt_question, all pointing to entry_id
    max_self_score: float        # ceiling for normalization (max BM25 self-similarity)
```

---

## BM25 Matching

### Tokenization (`rag/indexer.py` and `rag/retriever.py`, shared)

```python
_STOP = {"the", "a", "an", "of", "for", "is", "are", "which", "who", "in", "at", "do", "does"}

def tokenize(text: str) -> list[str]:
    words = re.findall(r'\b\w+\b', text.lower())
    return [w for w in words if w not in _STOP and len(w) > 1]
```

### Index Build (`rag/indexer.py`)

1. Read all lines from `faq.jsonl`, parse into `FAQEntry` objects.
2. Reject any entry whose `sql` matches `r'\b(insert|update|delete|drop|truncate|alter|create)\b'` (case-insensitive). Raise `ValueError` and abort.
3. Expand corpus: for each entry, one `CorpusDoc` per `question` + each item in `alt_questions`.
4. Build `BM25Okapi(corpus_tokens)`.
5. Compute `max_self_score`: for each corpus doc, score it against its own tokens using `bm25.get_scores(tokens)[i]`. Take the global max across all docs.
6. Write `faq_index.json`.

### Query-time Matching (`rag/retriever.py`)

```python
class RAGRetriever:
    DIRECT_THRESHOLD = 0.85
    FEW_SHOT_THRESHOLD = 0.60

    def search(self, query: str) -> MatchResult:
        tokens = tokenize(query)
        raw_scores = self._bm25.get_scores(tokens)
        best_raw = raw_scores.max()

        if best_raw == 0.0:
            return MatchResult(tier="MISS", entry=None, score=0.0, top_k=[])

        normalized = best_raw / self._index.max_self_score
        # Rank all docs by raw score, deduplicate by entry_id (keep highest-scoring doc per entry)
        # → ranked_entries: list[FAQEntry] ordered by score desc

        best_entry = ranked_entries[0]
        top3 = ranked_entries[:3]

        # Entries marked has_variables=True are never DIRECT-served (placeholder SQL)
        effective_tier_threshold = normalized
        if best_entry.has_variables:
            effective_tier_threshold = min(normalized, FEW_SHOT_THRESHOLD - 0.01)

        if effective_tier_threshold >= DIRECT_THRESHOLD:
            return MatchResult(tier="DIRECT", entry=best_entry, score=normalized, top_k=[])
        elif normalized >= FEW_SHOT_THRESHOLD:
            return MatchResult(tier="FEW_SHOT", entry=best_entry, score=normalized, top_k=top3)
        else:
            return MatchResult(tier="MISS", entry=None, score=normalized, top_k=[])
```

Deduplication: when the same `entry_id` appears via multiple corpus docs (primary + alts), keep only the highest-scoring doc for that entry before tiering.

---

## FAQ Corpus Plan (~50 entries)

### Student Management (15 entries)

| ID | Question | Intent |
|----|----------|--------|
| `student-count-total` | how many students are enrolled | AGGREGATION |
| `student-count-active` | how many active students | AGGREGATION |
| `student-count-by-class` | how many students in each class | AGGREGATION |
| `student-count-by-gender` | how many male and female students | AGGREGATION |
| `student-list-all` | list all students | FILTERED_LIST |
| `student-list-active` | show all active students | FILTERED_LIST |
| `student-list-by-class` | show students in class 5 | FILTERED_LIST |
| `student-list-by-section` | list students in section A | FILTERED_LIST |
| `student-list-by-gender-male` | list all male students | FILTERED_LIST |
| `student-list-by-gender-female` | list all female students | FILTERED_LIST |
| `student-list-by-status-withdrawn` | show withdrawn students | FILTERED_LIST |
| `student-list-blood-group` | students with blood group O positive | FILTERED_LIST |
| `student-lookup-by-name` | find student named Amudha | POINT_LOOKUP |
| `student-count-new-this-year` | how many students joined this academic year | TEMPORAL |
| `student-list-no-class` | students not assigned to any class | FILTERED_LIST |

### Staff Management (15 entries)

| ID | Question | Intent |
|----|----------|--------|
| `staff-count-total` | how many teachers are there | AGGREGATION |
| `staff-count-active` | total active staff count | AGGREGATION |
| `staff-count-by-gender` | how many male and female staff | AGGREGATION |
| `staff-count-by-category` | count staff by category | AGGREGATION |
| `staff-list-all` | list all staff | FILTERED_LIST |
| `staff-list-active` | show all active teachers | FILTERED_LIST |
| `staff-list-by-designation` | list all principals | FILTERED_LIST |
| `staff-list-by-department` | staff in science department | FILTERED_LIST |
| `staff-list-by-employment-type` | list contract staff | FILTERED_LIST |
| `staff-list-by-gender-female` | list all female teachers | FILTERED_LIST |
| `staff-list-tet-certified` | teachers with TET certification | FILTERED_LIST |
| `staff-list-with-qualification` | staff with B.Ed qualification | FILTERED_LIST |
| `staff-lookup-by-name` | find teacher named Ravi Kumar | POINT_LOOKUP |
| `staff-list-class-teachers` | show all class teachers | FILTERED_LIST |
| `staff-count-by-teaching-category` | how many teaching staff vs non-teaching | AGGREGATION |

### Classes & Sections (8 entries)

| ID | Question | Intent |
|----|----------|--------|
| `class-count-total` | how many classes are there | AGGREGATION |
| `class-list-all` | list all classes | FILTERED_LIST |
| `class-list-active` | show all active classes | FILTERED_LIST |
| `class-section-count` | how many sections per class | AGGREGATION |
| `class-most-students` | which class has the most students | COMPARATIVE |
| `class-fewest-students` | which class has the fewest students | COMPARATIVE |
| `class-section-list` | list all sections in class 6 | FILTERED_LIST |
| `class-student-count-each` | number of students in each class and section | AGGREGATION |

### Subjects (5 entries)

| ID | Question | Intent |
|----|----------|--------|
| `subject-list-all` | list all subjects | FILTERED_LIST |
| `subject-count-total` | how many subjects are offered | AGGREGATION |
| `subject-count-by-category` | count subjects by category | AGGREGATION |
| `subject-list-active` | show all active subjects | FILTERED_LIST |
| `subject-list-by-class` | what subjects does class 8 have | FILTERED_LIST |

### Academic Years (4 entries)

| ID | Question | Intent |
|----|----------|--------|
| `academic-year-current` | what is the current academic year | TEMPORAL |
| `academic-year-list` | list all academic years | FILTERED_LIST |
| `academic-year-active` | show active academic years | FILTERED_LIST |
| `academic-year-count` | how many academic years are configured | AGGREGATION |

### Admissions (3 entries)

| ID | Question | Intent |
|----|----------|--------|
| `admission-count-total` | how many admission applications are there | AGGREGATION |
| `admission-count-by-status` | count admissions by status | AGGREGATION |
| `admission-list-pending` | show pending admission applications | FILTERED_LIST |

---

## SQL Template Rules

All SQL in `faq.jsonl` must follow these rules (enforced at index build time and by convention):

1. **SELECT only** — no DML, DDL, or TCL. Indexer rejects on forbidden keyword match.
2. **No `school_id` literals** — the runner injects `AND {primary_table}.school_id = '{uuid}'`.
3. **Soft-delete guard** — tables with `deleted_at` must include `WHERE deleted_at IS NULL`.
4. **Parameterized filters** — entries with variable values (class name, person name) use `ILIKE '%placeholder%'` syntax; these are FEW_SHOT-only (never DIRECT-served since the placeholder won't match a specific query exactly).
5. **LIMIT** — all SQL must end with `LIMIT 100` (consistent with the pipeline default).

---

## Scripts

### `scripts/build_faq_index.py`

```
Usage: uv run python scripts/build_faq_index.py

Reads:  rag/faq.jsonl
Writes: rag/faq_index.json
Prints: entry count, corpus doc count, max_self_score
Errors: exits non-zero if any FAQ entry fails validation
```

### `scripts/test_faq_sql.py`

```
Usage: uv run python scripts/test_faq_sql.py

Reads:  rag/faq.jsonl, DB_URL from .env
For each entry: appends AND {primary_table}.school_id = '{TEST_SCHOOL_ID}' to SQL,
  executes against DB, prints: entry_id | row_count | PASS / ERROR: <message>
Env:    DB_URL, TEST_SCHOOL_ID (from .env or env override)
```

---

## Phase 3 Integration

### Changes to existing files (all minimal)

**`pyproject.toml`**
```toml
"rank_bm25>=0.2",
```

**`core/pipeline/graph.py`**  
Add one field to `PipelineState`:
```python
few_shot_examples: list[dict] | None  # set by RAGInterceptor for FEW_SHOT tier
```

**`core/retrieval_layer/intent_classifier.py`**  
`_llm_classify` gains an optional `few_shot_examples: list[dict] | None = None` parameter. When present, a section is appended to the LLM prompt:
```
Verified examples (high-confidence reference):
- "list all active students" → tables: [students], intent: FILTERED_LIST, filters: [{status ILIKE active}]
- ...
```

**`core/api/routes/query.py`**  
Wrap `_pipeline.invoke()`:
```python
from rag.interceptor import RAGInterceptor
_rag: RAGInterceptor | None = None

def init(pipeline, store):
    global _pipeline, _store, _rag
    _pipeline = pipeline
    _store = store
    _rag = RAGInterceptor()

# in run_query():
state = _rag.intercept(req.query, req.school_id, req.limit, _pipeline, runner, summarizer)
```

The interceptor takes the runner and summarizer instances so DIRECT-tier responses can bypass the pipeline while still using the production runner (school_id injection) and summarizer.

**`core/pipeline/graph.py`** — `build_pipeline()` currently returns only the compiled graph. Change it to return a named tuple `PipelineParts(graph, runner, summarizer)` so the interceptor can reuse the production runner and summarizer for DIRECT-tier responses without re-instantiating them. All callers (`core/api/main.py`) must be updated to unpack accordingly.

### RAGInterceptor behavior (`rag/interceptor.py`)

```
DIRECT tier:
  1. Substitute limit: sql = re.sub(r'LIMIT\s+\d+', f'LIMIT {limit}', entry.sql, flags=re.IGNORECASE)
  2. Create SQLResult(sql=sql, confidence_score=1.0, warnings=[], value_extractions={})
  3. runner.run(sql_result, school_id, entry.primary_table)  ← injects school_id, executes
  4. summarizer.summarize(query, run_result)                 ← LLM summarizer still runs
  5. Build and return QueryResponse (token_usage reflects summarizer cost only)

FEW_SHOT tier:
  1. Build few_shot_examples list from top_k entries (entry id, question, intent, tables, filters)
  2. pipeline.invoke({..., "few_shot_examples": few_shot_examples})
  3. Normal QueryResponse construction

MISS tier:
  1. pipeline.invoke({...})  ← unchanged, no few_shot_examples key
  2. Normal QueryResponse construction
```

---

## Testing Strategy

### Unit tests (`tests/unit/test_rag_retriever.py`)
- `tokenize()` correctness
- BM25 index build from minimal corpus
- `search()` returns correct tier for exact/near/unrelated queries
- Deduplication when same entry_id has multiple corpus docs
- DIRECT threshold respected

### Integration test (`tests/unit/test_faq_sql.py`)
- All entries in `faq.jsonl` parse without error
- No forbidden SQL keywords in any entry
- All `primary_table` values exist in `db/schema_index.json`

### E2E (Phase 3, run manually)
- Known FAQ query → 0 classifier/generator tokens in response
- Unknown query → normal token usage, pipeline runs fully
- FEW_SHOT query → classifier runs with examples injected, intent correct

---

## What This Does NOT Do

- Does not replace the pipeline for novel or complex queries.
- Does not handle parameterized queries (specific names, specific class names) as DIRECT — those always flow to the full pipeline (BM25 won't match with high confidence since the FAQ uses generic placeholders).
- Does not persist state between Vercel cold starts beyond what is already in `faq_index.json`.
- Does not add any authentication, rate limiting, or per-school FAQ customization.
