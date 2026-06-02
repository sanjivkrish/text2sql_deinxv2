from core.generation_layer.clause_builder import SQLClauseBuilder
from core.generation_layer.value_extractor import ValueExtractor
from core.generation_layer.output_validator import OutputValidator
from core.models.intent import QueryIntentJSON
from core.models.sql import SQLResult

class SQLGenerator:
    def __init__(self, schema: dict):
        self._builder = SQLClauseBuilder(schema)
        self._extractor = ValueExtractor()
        self._validator = OutputValidator()

    def generate(self, intent: QueryIntentJSON, limit: int = 100) -> SQLResult:
        # Fill any empty filter values via LLM
        if any(not f.value.strip() for f in intent.filters):
            filled_filters = self._extractor.fill_values(intent.filters, intent.query_metadata.raw_query)
            intent = intent.model_copy(update={"filters": filled_filters})

        result = self._builder.build(intent, limit=limit)
        report = self._validator.validate(result)

        final_warnings = list(result.warnings) + report["warnings"]
        return SQLResult(
            sql=result.sql,
            confidence_score=result.confidence_score if report["is_valid"] else 0.0,
            warnings=final_warnings,
            value_extractions=result.value_extractions,
        )
