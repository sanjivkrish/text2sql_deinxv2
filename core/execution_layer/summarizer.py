import json
import os
import litellm
from core.models.result import QueryRunResult, TokenUsage

# Cost per 1M tokens — groq/llama-3.3-70b-versatile pricing (update when model changes)
_COST_PER_INPUT_TOKEN = 0.59 / 1_000_000   # $0.59/M input
_COST_PER_OUTPUT_TOKEN = 0.79 / 1_000_000  # $0.79/M output


class ResultSummarizer:
    def summarize(self, query: str, run_result: QueryRunResult) -> tuple[str, TokenUsage]:
        rows_preview = run_result.rows[:20]  # cap context
        prompt = (
            f"The user asked: \"{query}\"\n"
            f"The query returned {run_result.row_count} rows.\n"
            f"Sample rows (up to 20): {json.dumps(rows_preview, default=str)}\n\n"
            "IMPORTANT: If the user's question expresses destructive intent (delete, drop, remove data, "
            "bypass rules, override security), respond ONLY with: "
            "'This system only supports read-only queries.' — do NOT use or describe the row data.\n\n"
            "Otherwise, answer the user's question directly using only the information in the rows above. "
            "Focus strictly on what was asked — if the question is about academic details, "
            "report academic fields (class, section, academic year, subjects) and skip unrelated fields. "
            "If the question is about a specific person, lead with that person's details. "
            "Do not mention SQL, row counts, or technical details. "
            "If rows are empty, say no results were found."
        )
        try:
            resp = litellm.completion(
                model=os.environ.get("LLM_MODEL", "claude-sonnet-4-6"),
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception:
            return "(summary unavailable)", TokenUsage(
                input_tokens=0, output_tokens=0, total_tokens=0, estimated_cost_usd=0.0
            )
        summary: str = resp.choices[0].message.content or "(no summary available)"
        usage = resp.usage
        in_tok: int = getattr(usage, "prompt_tokens", 0) or 0
        out_tok: int = getattr(usage, "completion_tokens", 0) or 0
        total_tok: int = getattr(usage, "total_tokens", 0) or 0
        cost = in_tok * _COST_PER_INPUT_TOKEN + out_tok * _COST_PER_OUTPUT_TOKEN

        return summary, TokenUsage(
            input_tokens=in_tok,
            output_tokens=out_tok,
            total_tokens=total_tok,
            estimated_cost_usd=round(cost, 6),
        )
