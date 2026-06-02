import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from core.api.middleware.auth import InternalTokenMiddleware
from core.api.middleware.rate_limit import InProcessRateLimitMiddleware
from core.api.routes import query as query_routes, schema as schema_routes, health as health_routes
from core.schema_layer.graph_store import GraphStore
from core.pipeline.graph import build_pipeline

_pipeline = None
_store = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pipeline, _store
    schema_path = os.environ.get("SCHEMA_PATH", "db/schema_index.json")
    db_url = os.environ.get("DB_URL", "")
    _store = GraphStore(schema_path)
    _store.load()
    parts = build_pipeline(schema_path=schema_path, db_url=db_url)
    _pipeline = parts.graph
    query_routes.init(parts.graph, _store)
    schema_routes.init(_store)
    health_routes.init(_store, db_url)
    yield

app = FastAPI(title="Text-to-SQL v2", lifespan=lifespan)
app.add_middleware(InternalTokenMiddleware)
app.add_middleware(InProcessRateLimitMiddleware)
app.include_router(query_routes.router)
app.include_router(schema_routes.router)
app.include_router(health_routes.router)
