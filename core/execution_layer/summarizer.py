import json
import os
import litellm
from core.models.result import QueryRunResult, TokenUsage

# Cost per 1M tokens (approximate, update when model changes)
_COST_PER_INPUT_TOKEN = 3.0 / 1_000_000   # $3/M input
_COST_PER_OUTPUT_TOKEN = 15.0 / 1_000_000  # $15/M output


class ResultSummarizer:
    def summarize(self, query: str, run_result: QueryRunResult) -> tuple[str, TokenUsage]:
        rows_preview = run_result.rows[:20]  # cap context
        prompt = (
            f"The user asked: \"{query}\"\n"
            f"The query returned {run_result.row_count} rows.\n"
            f"Sample rows (up to 20): {json.dumps(rows_preview, default=str)}\n\n"
            "Write a concise natural-language summary of the results. "
            "Do not mention SQL or technical details. "
            "If rows are empty, say no results were found."
        )
        resp = litellm.completion(
            model=os.environ.get("LLM_MODEL", "claude-sonnet-4-6"),
            messages=[{"role": "user", "content": prompt}],
        )
        summary: str = resp.choices[0].message.content
        in_tok: int = resp.usage.prompt_tokens
        out_tok: int = resp.usage.completion_tokens
        total_tok: int = resp.usage.total_tokens
        cost = in_tok * _COST_PER_INPUT_TOKEN + out_tok * _COST_PER_OUTPUT_TOKEN

        return summary, TokenUsage(
            input_tokens=in_tok,
            output_tokens=out_tok,
            total_tokens=total_tok,
            estimated_cost_usd=round(cost, 6),
        )
