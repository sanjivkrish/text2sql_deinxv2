from pydantic import BaseModel, field_validator

class ResolvedEntity(BaseModel):
    raw_text: str
    table: str
    column: str | None
    confidence: float

    @field_validator('confidence')
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError('confidence must be between 0.0 and 1.0')
        return v

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

    @field_validator('confidence')
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError('confidence must be between 0.0 and 1.0')
        return v
