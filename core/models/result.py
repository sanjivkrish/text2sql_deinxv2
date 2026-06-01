from pydantic import BaseModel

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
