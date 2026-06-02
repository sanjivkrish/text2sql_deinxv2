import json
import os
import litellm
from core.models.intent import FilterCondition

class ValueExtractor:
    def fill_values(self, filters: list[FilterCondition], query: str) -> list[FilterCondition]:
        empty = [f for f in filters if not f.value.strip()]
        if not empty:
            return filters

        keys = [f"{f.table}.{f.column}" for f in empty]
        prompt = (
            f"Given the query: \"{query}\"\n"
            f"Extract the filter values for these fields: {keys}\n"
            f"Return JSON: {{\"values\": {{\"table.column\": \"extracted_value\"}}}}"
        )
        resp = litellm.completion(
            model=os.environ.get("LLM_MODEL", "claude-sonnet-4-6"),
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content
        try:
            data = json.loads(content) if content else {}
        except (json.JSONDecodeError, TypeError):
            data = {}
        extracted: dict[str, str] = data.get("values", {})

        updated: list[FilterCondition] = []
        for f in filters:
            key = f"{f.table}.{f.column}"
            if key in extracted and not f.value.strip():
                updated.append(f.model_copy(update={"value": extracted[key]}))
            else:
                updated.append(f)
        return updated
