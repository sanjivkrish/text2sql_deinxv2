import time
from collections import defaultdict
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

class InProcessRateLimitMiddleware(BaseHTTPMiddleware):
    """Failsafe in-process rate limit. Primary is Cloudflare KV."""
    def __init__(self, app, max_requests: int = 120, window_seconds: int = 60):
        super().__init__(app)
        self._max = max_requests
        self._window = window_seconds
        self._counts: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        key = (
            request.headers.get("X-User-ID")
            or request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            or (request.client.host if request.client else "unknown")
        )
        now = time.monotonic()
        self._counts[key] = [t for t in self._counts[key] if now - t < self._window]
        if len(self._counts[key]) >= self._max:
            return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})
        self._counts[key].append(now)
        return await call_next(request)
