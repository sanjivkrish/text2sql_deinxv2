import networkx as nx
from core.models.query import TraversalResult

class TraversalEngine:
    def __init__(self, graph: nx.DiGraph):
        self._graph = graph

    def find_path(self, from_table: str, to_table: str) -> TraversalResult | None:
        src, dst = f"tbl_{from_table}", f"tbl_{to_table}"
        if src not in self._graph or dst not in self._graph:
            return None
        if src == dst:
            return TraversalResult(path=[from_table], join_sql=[], hop_count=0)

        # Only traverse table→table FK edges (not column edges)
        tbl_graph = nx.DiGraph()
        for u, v, data in self._graph.edges(data=True):
            if data.get("rel") == "fk":
                tbl_graph.add_edge(u, v, **data)

        try:
            path_nodes = nx.shortest_path(tbl_graph, src, dst)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

        join_sql: list[str] = []
        for i in range(len(path_nodes) - 1):
            edge = tbl_graph[path_nodes[i]][path_nodes[i + 1]]
            join_sql.append(edge["join_sql"])

        table_path = [n[4:] for n in path_nodes]  # strip "tbl_"
        return TraversalResult(path=table_path, join_sql=join_sql,
                               hop_count=len(path_nodes) - 1)
