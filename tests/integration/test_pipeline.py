import pytest
from unittest.mock import MagicMock, patch
from core.pipeline.graph import build_pipeline

MOCK_SCHOOL_ID = "a0000000-0000-0000-0000-000000000001"


@pytest.fixture
def mock_components(tmp_path):
    """Build graph with test schema_index.json."""
    import json
    from core.schema_layer.graph_builder import GraphBuilder
    from core.schema_layer.graph_store import GraphStore

    schema = {
        "tables": {
            "schools": {
                "columns": [{"name": "id", "type": "uuid", "nullable": False}],
                "has_soft_delete": False,
                "has_school_id": False,
            },
            "students": {
                "columns": [
                    {"name": "id", "type": "uuid", "nullable": False},
                    {"name": "school_id", "type": "uuid", "nullable": False},
                    {"name": "full_name", "type": "text", "nullable": True},
                ],
                "has_soft_delete": False,
                "has_school_id": True,
            },
        },
        "foreign_keys": [
            {
                "from_table": "students",
                "from_column": "school_id",
                "to_table": "schools",
                "to_column": "id",
            }
        ],
    }
    g = GraphBuilder(schema).build()
    path = str(tmp_path / "schema_index.json")
    GraphStore(path).save(g, schema)
    return path


def test_pipeline_returns_query_response(mock_components):
    with patch("core.execution_layer.runner.psycopg") as mock_psycopg, \
         patch("litellm.completion") as mock_llm:
        # Mock DB execution
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.__enter__ = lambda s: mock_cur
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_cur.fetchall.return_value = [
            {"full_name": "Alice", "school_id": MOCK_SCHOOL_ID}
        ]
        mock_conn.__enter__ = lambda s: mock_conn
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cur
        mock_psycopg.connect.return_value = mock_conn

        # Mock LLM summarizer
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = "There is 1 student."
        mock_resp.usage.prompt_tokens = 100
        mock_resp.usage.completion_tokens = 20
        mock_resp.usage.total_tokens = 120
        mock_llm.return_value = mock_resp

        import os
        os.environ["DB_URL"] = "postgresql://mock"

        pipeline = build_pipeline(
            schema_path=mock_components, db_url="postgresql://mock"
        )
        result = pipeline.invoke(
            {
                "query": "list all students",
                "school_id": MOCK_SCHOOL_ID,
                "limit": 10,
            }
        )
        assert result.get("summary") is not None
        assert result.get("token_usage") is not None
        assert result.get("error") is None
