from pydantic import BaseModel, field_validator

class QueryRunResult(BaseModel):
    rows: list[dict]
    row_count: int
    execution_time_ms: float
    sql: str  # school_id-injected SQL that actually ran

class TokenUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float

class QueryResponse(BaseModel):
    query: str
    school_id: str  # UUID
    summary: str
    token_usage: TokenUsage
    confidence: float
    warnings: list[str]
    timing: dict[str, float]
    sql: str | None = None  # school_id-injected SQL that executed; None for plan-only

    @field_validator('confidence')
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError('confidence must be between 0.0 and 1.0')
        return v
