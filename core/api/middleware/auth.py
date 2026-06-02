import os
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

EXCLUDED_PATHS = {"/health", "/docs", "/openapi.json"}

class InternalTokenMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in EXCLUDED_PATHS:
            return await call_next(request)
        token = request.headers.get("X-Internal-Token")
        expected = os.environ.get("INTERNAL_SECRET", "")
        if not expected or token != expected:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
        return await call_next(request)
