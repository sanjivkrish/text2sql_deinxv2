from fastapi import APIRouter, HTTPException
from core.schema_layer.graph_store import GraphStore

router = APIRouter()
_store: GraphStore | None = None


def init(store: GraphStore):
    global _store
    _store = store


@router.get("/schema/tables")
def schema_tables():
    if _store is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    schema = _store.schema
    return {
        table: [c["name"] for c in meta["columns"]]
        for table, meta in schema["tables"].items()
    }
