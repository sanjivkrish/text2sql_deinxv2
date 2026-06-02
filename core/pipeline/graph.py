from typing import TypedDict, NamedTuple
from langgraph.graph import StateGraph, END
from core.models.query import QueryPlan
from core.models.intent import QueryIntentJSON
from core.models.sql import SQLResult
from core.models.result import QueryRunResult, TokenUsage
from core.schema_layer.graph_store import GraphStore
from core.retrieval_layer.semantic_mapper import SemanticMapper
from core.retrieval_layer.traversal import TraversalEngine
from core.retrieval_layer.query_planner import QueryGraphPlanner
from core.retrieval_layer.intent_classifier import IntentClassifier
from core.generation_layer.sql_generator import SQLGenerator
from core.execution_layer.runner import SQLRunner
from core.execution_layer.summarizer import ResultSummarizer


class PipelineState(TypedDict, total=False):
    query: str
    school_id: str
    limit: int
    query_plan: QueryPlan | None
    intent: QueryIntentJSON | None
    sql_result: SQLResult | None
    run_result: QueryRunResult | None
    summary: str | None
    token_usage: TokenUsage | None
    error: str | None
    few_shot_examples: list[dict] | None


class PipelineParts(NamedTuple):
    graph: object
    runner: "SQLRunner"
    summarizer: "ResultSummarizer"


def build_pipeline(schema_path: str = "db/schema_index.json", db_url: str = ""):
    store = GraphStore(schema_path)
    graph, schema = store.load()

    mapper = SemanticMapper(graph, schema)
    engine = TraversalEngine(graph)
    planner = QueryGraphPlanner(mapper, engine, schema)
    classifier = IntentClassifier()
    generator = SQLGenerator(schema)
    runner = SQLRunner(db_url)
    summarizer = ResultSummarizer()

    def planner_node(state: PipelineState) -> PipelineState:
        plan = planner.plan(state["query"])
        return {**state, "query_plan": plan}

    def classifier_node(state: PipelineState) -> PipelineState:
        try:
            intent = classifier.classify(state["query"], state["query_plan"])
            return {**state, "intent": intent}
        except Exception as e:
            return {**state, "error": str(e)}

    def generator_node(state: PipelineState) -> PipelineState:
        if state.get("error") or state.get("intent") is None:
            return state
        try:
            result = generator.generate(state["intent"], limit=state.get("limit", 100))
            return {**state, "sql_result": result}
        except Exception as e:
            return {**state, "error": str(e)}

    def validator_router(state: PipelineState) -> str:
        """Routing function for conditional edges after 'validator' pass-through node."""
        if state.get("sql_result") is None or state.get("error"):
            return "error_node"
        from core.generation_layer.output_validator import OutputValidator
        report = OutputValidator().validate(state["sql_result"])
        if report["is_valid"]:
            return "executor"
        return "error_node"

    def executor_node(state: PipelineState) -> PipelineState:
        if state.get("error") or state.get("intent") is None:
            return state
        try:
            tables = state["intent"].structural_plan.tables
            primary_table = tables[0] if tables else "students"
            run_result = runner.run(state["sql_result"], state["school_id"], primary_table)
            return {**state, "run_result": run_result}
        except Exception as e:
            return {**state, "error": str(e)}

    def summarizer_node(state: PipelineState) -> PipelineState:
        if state.get("error"):
            return {**state,
                    "summary": f"Error: {state['error']}",
                    "token_usage": TokenUsage(input_tokens=0, output_tokens=0, total_tokens=0, estimated_cost_usd=0.0)}
        summary, usage = summarizer.summarize(state["query"], state["run_result"])
        return {**state, "summary": summary, "token_usage": usage}

    def error_node(state: PipelineState) -> PipelineState:
        err = state.get("error") or "SQL validation failed"
        return {**state, "summary": f"Error: {err}", "token_usage": TokenUsage(
            input_tokens=0, output_tokens=0, total_tokens=0, estimated_cost_usd=0.0
        )}

    sg = StateGraph(PipelineState)
    sg.add_node("planner", planner_node)
    sg.add_node("classifier", classifier_node)
    sg.add_node("generator", generator_node)
    sg.add_node("validator", lambda s: s)  # routing node — state pass-through
    sg.add_node("executor", executor_node)
    sg.add_node("summarizer", summarizer_node)
    sg.add_node("error_node", error_node)

    sg.set_entry_point("planner")
    sg.add_edge("planner", "classifier")
    sg.add_edge("classifier", "generator")
    sg.add_edge("generator", "validator")
    sg.add_conditional_edges(
        "validator",
        validator_router,
        {"executor": "executor", "error_node": "error_node"},
    )
    sg.add_edge("executor", "summarizer")
    sg.add_edge("summarizer", END)
    sg.add_edge("error_node", END)

    return PipelineParts(graph=sg.compile(), runner=runner, summarizer=summarizer)
