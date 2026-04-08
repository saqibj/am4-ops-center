"""Request profiling: query count, db time, handler time, response bytes."""

from __future__ import annotations

import json
import logging
import time
from contextvars import ContextVar
from dataclasses import dataclass

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import HTMLResponse, Response

logger = logging.getLogger("am4.profiling")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s %(name)s: %(message)s"))
    logger.addHandler(_handler)
    logger.propagate = False
logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# Per-request metrics accumulated via contextvar
# ---------------------------------------------------------------------------


@dataclass
class RequestMetrics:
    query_count: int = 0
    db_ms: float = 0.0

    def record_query(self, elapsed_s: float) -> None:
        self.query_count += 1
        self.db_ms += elapsed_s * 1000


_request_metrics: ContextVar[RequestMetrics | None] = ContextVar(
    "_request_metrics", default=None
)


def get_request_metrics() -> RequestMetrics | None:
    return _request_metrics.get()


# ---------------------------------------------------------------------------
# Connection instrumentation — wraps sqlite3.Connection.execute()
# ---------------------------------------------------------------------------


class _InstrumentedConnection:
    """Thin proxy that times execute()/executemany() calls."""

    __slots__ = ("_conn", "_metrics")

    def __init__(self, conn, metrics: RequestMetrics) -> None:
        self._conn = conn
        self._metrics = metrics

    def execute(self, *args, **kwargs):
        t0 = time.perf_counter()
        try:
            return self._conn.execute(*args, **kwargs)
        finally:
            self._metrics.record_query(time.perf_counter() - t0)

    def executemany(self, *args, **kwargs):
        t0 = time.perf_counter()
        try:
            return self._conn.executemany(*args, **kwargs)
        finally:
            self._metrics.record_query(time.perf_counter() - t0)

    def __enter__(self):
        return self._conn.__enter__()

    def __exit__(self, *args):
        return self._conn.__exit__(*args)

    def __getattr__(self, name):
        return getattr(self._conn, name)


def instrument_connection(conn):
    """Return an instrumented wrapper if a profiling context is active."""
    metrics = _request_metrics.get()
    if metrics is None:
        return conn
    return _InstrumentedConnection(conn, metrics)


# ---------------------------------------------------------------------------
# Main profiling middleware
# ---------------------------------------------------------------------------

_SKIP_PREFIXES = ("/static/", "/favicon.ico")


class ProfilingMiddleware(BaseHTTPMiddleware):
    """Logs per-request metrics; injects ``<!-- perf: {...} -->`` when ``?debug=1``."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path
        if any(path.startswith(p) for p in _SKIP_PREFIXES):
            return await call_next(request)

        metrics = RequestMetrics()
        token = _request_metrics.set(metrics)

        t0 = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            total_ms = (time.perf_counter() - t0) * 1000
            _request_metrics.reset(token)

        debug = request.query_params.get("debug") == "1"
        is_html = "text/html" in response.headers.get("content-type", "")

        if debug and is_html:
            body = b""
            async for chunk in response.body_iterator:
                body += chunk if isinstance(chunk, bytes) else chunk.encode("utf-8")
            response_bytes = len(body)

            perf = {
                "route": path,
                "method": request.method,
                "status": response.status_code,
                "total_ms": round(total_ms, 2),
                "db_ms": round(metrics.db_ms, 2),
                "query_count": metrics.query_count,
                "response_bytes": response_bytes,
            }
            body += f"\n<!-- perf: {json.dumps(perf)} -->".encode("utf-8")

            logger.info(
                "%-6s %s -> %d | total=%.1fms db=%.1fms queries=%d size=%dB [debug]",
                request.method,
                path,
                response.status_code,
                total_ms,
                metrics.db_ms,
                metrics.query_count,
                response_bytes,
            )

            headers = dict(response.headers)
            headers["content-length"] = str(len(body))
            return Response(
                content=body,
                status_code=response.status_code,
                headers=headers,
                media_type=response.media_type,
            )

        response_bytes = int(response.headers.get("content-length", 0))
        logger.info(
            "%-6s %s -> %d | total=%.1fms db=%.1fms queries=%d size=%dB",
            request.method,
            path,
            response.status_code,
            total_ms,
            metrics.db_ms,
            metrics.query_count,
            response_bytes,
        )
        return response


# ---------------------------------------------------------------------------
# Optional pyinstrument flamegraph middleware (PROFILE=1)
# ---------------------------------------------------------------------------


class PyInstrumentMiddleware(BaseHTTPMiddleware):
    """Return a pyinstrument HTML flamegraph for any request with ``?profile=1``.

    Only active when the ``PROFILE=1`` env-var is set **and** pyinstrument is installed.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.query_params.get("profile") != "1":
            return await call_next(request)
        try:
            from pyinstrument import Profiler
        except ImportError:
            return await call_next(request)

        profiler = Profiler(async_mode="enabled")
        profiler.start()
        try:
            await call_next(request)
        finally:
            profiler.stop()
        return HTMLResponse(profiler.output_html())
