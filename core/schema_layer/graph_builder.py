import networkx as nx


class GraphBuilder:
    def __init__(self, schema: dict):
        self._schema = schema

    def build(self) -> nx.DiGraph:
        g = nx.DiGraph()
        tables = self._schema["tables"]

        for table_name, meta in tables.items():
            tbl_node = f"tbl_{table_name}"
            g.add_node(tbl_node, type="table", table=table_name,
                       has_soft_delete=meta["has_soft_delete"],
                       has_school_id=meta["has_school_id"])
            for col in meta["columns"]:
                col_node = f"col_{table_name}.{col['name']}"
                g.add_node(col_node, type="column", table=table_name,
                           column=col["name"], dtype=col["type"],
                           nullable=col["nullable"])
                g.add_edge(tbl_node, col_node, rel="has_column")

        for fk in self._schema["foreign_keys"]:
            ft, fc, tt, tc = fk["from_table"], fk["from_column"], fk["to_table"], fk["to_column"]
            if f"tbl_{ft}" not in g or f"tbl_{tt}" not in g:
                continue
            join_sql = f"{ft}.{fc} = {tt}.{tc}"
            g.add_edge(f"tbl_{ft}", f"tbl_{tt}",
                       rel="fk", join_sql=join_sql,
                       from_col=fc, to_col=tc)

        return g
