import re
import time
from rag.retriever import RAGRetriever
from rag.models import MatchResult
from core.models.sql import SQLResult
from core.models.result import TokenUsage


class RAGInterceptor:
    def __init__(self, index_path: str = "rag/faq_index.json"):
        self._retriever = RAGRetriever(index_path)

    def intercept(
        self,
        query: str,
        school_id: str,
        limit: int,
        pipeline,
        runner,
        summarizer,
    ) -> dict:
        """Return a pipeline-compatible state dict.

        DIRECT tier: bypass planner/classifier/generator; execute FAQ SQL directly.
        FEW_SHOT tier: inject top-k as few_shot_examples into pipeline state.
        MISS tier: invoke pipeline unchanged.
        """
        match: MatchResult = self._retriever.search(query)

        if match.tier == "DIRECT":
            return self._direct(query, school_id, limit, match, runner, summarizer)
        elif match.tier == "FEW_SHOT":
            few_shot = [
                {
                    "question": e.question,
                    "intent": e.intent,
                    "tables": [e.primary_table],
                    "domain": e.domain,
                }
                for e in match.top_k
            ]
            return pipeline.invoke({
                "query": query,
                "school_id": school_id,
                "limit": limit,
                "few_shot_examples": few_shot,
            })
        else:
            return pipeline.invoke({
                "query": query,
                "school_id": school_id,
                "limit": limit,
            })

    def _direct(self, query: str, school_id: str, limit: int, match: MatchResult, runner, summarizer) -> dict:
        entry = match.entry
        # Substitute LIMIT placeholder with the actual request limit
        sql = re.sub(r'\bLIMIT\s+\d+\b', f'LIMIT {limit}', entry.sql, flags=re.IGNORECASE)
        sql_result = SQLResult(sql=sql, confidence_score=1.0, warnings=[], value_extractions={})
        try:
            run_result = runner.run(sql_result, school_id, entry.primary_table)
        except Exception as e:
            return {
                "query": query,
                "school_id": school_id,
                "error": str(e),
                "summary": f"Error: {e}",
                "token_usage": TokenUsage(input_tokens=0, output_tokens=0, total_tokens=0, estimated_cost_usd=0.0),
            }
        summary, usage = summarizer.summarize(query, run_result)
        return {
            "query": query,
            "school_id": school_id,
            "sql_result": sql_result,
            "run_result": run_result,
            "summary": summary,
            "token_usage": usage,
            "error": None,
        }
