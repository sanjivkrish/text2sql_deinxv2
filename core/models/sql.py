from pydantic import BaseModel

class SQLResult(BaseModel):
    sql: str
    confidence_score: float
    warnings: list[str]
    value_extractions: dict[str, str]
