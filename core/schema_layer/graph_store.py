import json
import networkx as nx
from networkx.readwrite import json_graph


class GraphStore:
    def __init__(self, path: str = "db/schema_index.json"):
        self._path = path
        self._graph: nx.DiGraph | None = None
        self._schema: dict | None = None

    def save(self, graph: nx.DiGraph, schema: dict) -> None:
        data = {
            "graph": json_graph.node_link_data(graph),
            "schema": schema,
        }
        with open(self._path, "w") as f:
            json.dump(data, f, indent=2)

    def load(self) -> tuple[nx.DiGraph, dict]:
        if self._graph is not None:
            return self._graph, self._schema  # type: ignore[return-value]
        with open(self._path) as f:
            data = json.load(f)
        self._graph = json_graph.node_link_graph(data["graph"], directed=True, multigraph=False)
        self._schema = data["schema"]
        return self._graph, self._schema

    @property
    def graph(self) -> nx.DiGraph:
        if self._graph is None:
            self.load()
        return self._graph  # type: ignore[return-value]

    @property
    def schema(self) -> dict:
        if self._schema is None:
            self.load()
        return self._schema  # type: ignore[return-value]
