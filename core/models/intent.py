from pydantic import BaseModel

class QueryMetadata(BaseModel):
    raw_query: str
    primary_domain: str
    operational_intent: str
    confidence: float

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
