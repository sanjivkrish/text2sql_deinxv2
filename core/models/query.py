from pydantic import BaseModel

class ResolvedEntity(BaseModel):
    raw_text: str
    table: str
    column: str | None
    confidence: float

class TraversalResult(BaseModel):
    path: list[str]
    join_sql: list[str]
    hop_count: int

class QueryPlan(BaseModel):
    resolved_entities: list[ResolvedEntity]
    join_paths: list[TraversalResult]
    recommended_tables: list[str]
    recommended_joins: list[str]
    confidence: float
