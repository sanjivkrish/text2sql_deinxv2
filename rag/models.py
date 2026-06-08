from typing import Literal
from pydantic import BaseModel


class FAQEntry(BaseModel):
    id: str
    question: str
    alt_questions: list[str]
    sql: str
    primary_table: str
    intent: str
    domain: str
    has_variables: bool = False


class CorpusDoc(BaseModel):
    tokens: list[str]
    entry_id: str


class FAQIndex(BaseModel):
    version: int
    built_at: str
    entries: list[FAQEntry]
    corpus: list[CorpusDoc]
    max_self_score: float


class MatchResult(BaseModel):
    tier: Literal["DIRECT", "FEW_SHOT", "MISS"]
    entry: FAQEntry | None
    score: float
    top_k: list[FAQEntry]
