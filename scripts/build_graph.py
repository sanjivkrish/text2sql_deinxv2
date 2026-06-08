#!/usr/bin/env python3
"""Run this against a live DB to regenerate db/schema_index.json."""
import os, sys
sys.path.insert(0, ".")
import psycopg
from core.schema_layer.extractor import SchemaExtractor
from core.schema_layer.graph_builder import GraphBuilder
from core.schema_layer.graph_store import GraphStore


def main():
    db_url = os.environ["DB_URL"]
    output = os.environ.get("SCHEMA_OUTPUT", "db/schema_index.json")
    with psycopg.connect(db_url, prepare_threshold=0) as conn:
        schema = SchemaExtractor(conn).extract()
    graph = GraphBuilder(schema).build()
    GraphStore(output).save(graph, schema)
    n_tables = len(schema["tables"])
    n_fks = len(schema["foreign_keys"])
    print(f"Built graph: {n_tables} tables, {n_fks} FK edges → {output}")


if __name__ == "__main__":
    main()
