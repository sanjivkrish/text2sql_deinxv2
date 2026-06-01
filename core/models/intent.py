from pydantic import BaseModel, field_validator

class QueryMetadata(BaseModel):
    raw_query: str
    primary_domain: str
    operational_intent: str
    confidence: float

    @field_validator('confidence')
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError('confidence must be between 0.0 and 1.0')
        return v

class FilterCondition(BaseModel):
    table: str
    column: str
    operator: str
    value: str
    value_type: str

class Aggregation(BaseModel):
    table: str
    column: str
    function: str

class Ordering(BaseModel):
    table: str
    column: str
    direction: str

class StructuralPlan(BaseModel):
    tables: list[str]
    join_conditions: list[str]
    select_columns: list[str]

class QueryIntentJSON(BaseModel):
    query_metadata: QueryMetadata
    structural_plan: StructuralPlan
    filters: list[FilterCondition]
    aggregations: list[Aggregation]
    ordering: list[Ordering]
