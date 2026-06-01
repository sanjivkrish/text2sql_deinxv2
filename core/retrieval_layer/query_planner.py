import re
from core.models.query import QueryPlan, ResolvedEntity, TraversalResult
from core.retrieval_layer.semantic_mapper import SemanticMapper
from core.retrieval_layer.traversal import TraversalEngine

def _tokenize(query: str) -> list[str]:
    tokens = re.findall(r'\b\w[\w\s]*\b', query.lower())
    return [t.strip() for t in tokens if len(t.strip()) > 2]

class QueryGraphPlanner:
    def __init__(self, mapper: SemanticMapper, engine: TraversalEngine, schema: dict):
        self._mapper = mapper
        self._engine = engine
        self._schema = schema

    def plan(self, query: str) -> QueryPlan:
        tokens = _tokenize(query)
        all_entities: list[ResolvedEntity] = []
        for token in tokens:
            all_entities.extend(self._mapper.map(token))

        # Deduplicate — highest confidence per (table, column)
        best: dict[tuple, ResolvedEntity] = {}
        for e in all_entities:
            key = (e.table, e.column)
            if key not in best or e.confidence > best[key].confidence:
                best[key] = e
        resolved = list(best.values())

        tables = list({e.table for e in resolved})
        join_paths: list[TraversalResult] = []
        recommended_joins: list[str] = []

        for i in range(len(tables)):
            for j in range(i + 1, len(tables)):
                path = self._engine.find_path(tables[i], tables[j])
                if path and path.hop_count > 0:
                    join_paths.append(path)
                    recommended_joins.extend(path.join_sql)

        confidence = max((e.confidence for e in resolved), default=0.5)

        return QueryPlan(
            resolved_entities=resolved,
            join_paths=join_paths,
            recommended_tables=tables,
            recommended_joins=list(dict.fromkeys(recommended_joins)),
            confidence=confidence,
        )
