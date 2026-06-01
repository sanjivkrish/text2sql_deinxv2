import re
import networkx as nx
from core.models.query import ResolvedEntity

# Synonym map: NL term → canonical table name
TABLE_SYNONYMS: dict[str, list[str]] = {
    "students": ["student", "students", "pupil", "learner", "child", "children"],
    "staff": ["staff", "teacher", "teachers", "teaching", "employee", "employees",
              "instructor", "faculty"],
    "classes": ["class", "classes", "grade", "standard", "level"],
    "class_sections": ["section", "sections", "division"],
    "subjects": ["subject", "subjects", "course", "paper"],
    "academic_years": ["academic year", "academic_year", "year", "session"],
    "admission_applications": ["admission", "admissions", "application", "applicant"],
    "schools": ["school", "institute", "institution"],
}

COLUMN_SYNONYMS: dict[str, list[str]] = {
    "full_name": ["name", "full name", "student name", "pupil name"],
    "date_of_birth": ["dob", "date of birth", "birth date", "age"],
    "designation": ["designation", "role", "title", "post"],
    "grade_level": ["grade level", "grade", "standard"],
    "is_current": ["current", "active year", "this year"],
    "status": ["status", "state"],
    "employment_type": ["employment type", "type of employment"],
    "staff_category": ["category", "staff category", "staff type"],
}

def _normalize(text: str) -> str:
    return re.sub(r"[_\-]", " ", text.lower().strip())


def _token_matches_synonym(norm: str, s: str) -> bool:
    if s in norm:
        return True
    # Only allow reverse-substring for multi-word synonyms to avoid "in" → "instructor"
    if " " in s and norm in s:
        return True
    return False


class SemanticMapper:
    def __init__(self, graph: nx.DiGraph, schema: dict):
        self._graph = graph
        self._schema = schema

    def map(self, token: str) -> list[ResolvedEntity]:
        norm = _normalize(token)
        results: list[ResolvedEntity] = []

        # Table matching
        for table, synonyms in TABLE_SYNONYMS.items():
            if table not in self._schema["tables"]:
                continue
            if f"tbl_{table}" not in self._graph:
                continue
            if any(_token_matches_synonym(norm, s) for s in synonyms):
                results.append(ResolvedEntity(
                    raw_text=token, table=table, column=None, confidence=0.85
                ))

        # Direct table name match
        for table in self._schema["tables"]:
            if f"tbl_{table}" not in self._graph:
                continue
            if _normalize(table) in norm or norm in _normalize(table):
                if not any(r.table == table for r in results):
                    results.append(ResolvedEntity(
                        raw_text=token, table=table, column=None, confidence=0.9
                    ))

        # Column matching — search across all tables
        for col_key, synonyms in COLUMN_SYNONYMS.items():
            if any(_token_matches_synonym(norm, s) for s in synonyms):
                for table, meta in self._schema["tables"].items():
                    if any(c["name"] == col_key for c in meta["columns"]):
                        results.append(ResolvedEntity(
                            raw_text=token, table=table, column=col_key, confidence=0.8
                        ))

        return results
