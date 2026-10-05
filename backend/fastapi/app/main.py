"""FastAPI application - Phase 2 telemetry service.

Layout:

    app/core/config.py   settings (env only; JWT key has no default)
    app/core/security.py local JWT verification, the trust boundary with Django
    app/db.py            async engine + session factory
    app/models.py        the `telemetry` schema
    app/schemas.py       pydantic request/response models + per-sensor ranges
    app/registry.py      known-session lookup and viewer permissions
    app/hub.py           in-process WebSocket fan-out
    app/errors.py        one error shape for everything
    app/routes/          sensor.py (device + user), internal.py (Django -> here)
    app/ws.py            WS /ws/sensor

This service stores and serves screening data; it is a screening aid, not a
medical diagnosis.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import MAX_PAYLOAD_BYTES, settings
from app.db import create_all, engine
from app.errors import error_body, install_error_handlers
from app.routes import internal, sensor
from app.ws import router as websocket_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Convenient for a first run and for the SQLite test database. PostgreSQL in
    # production is owned by Alembic (`alembic upgrade head`), which creates the
    # schema first; create_all is then a no-op.
    await create_all()
    logger.info(
        "telemetry ready: schema=%s heartbeat=%ss",
        settings.telemetry_schema_name or "<none>",
        settings.heartbeat_threshold_seconds,
    )
    yield
    await engine.dispose()


app = FastAPI(
    title="ECG telemetry API",
    version="2.0.0",
    description=(
        "Storage and live delivery of sensor data for the AI-Based ECG "
        "Diagnostic Assistant. A screening aid, not a medical diagnosis."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def limit_payload_size(request: Request, call_next):
    """Refuse an oversized body before it is parsed.

    Checked here rather than in the schema because a body that is well-formed
    but enormous must answer `413`, not the `422` the JSON parser would give it.
    Reading the body costs nothing extra: the middleware caches it and the route
    re-reads the same bytes.
    """
    if request.method in {"POST", "PUT", "PATCH"}:
        body = await request.body()
        if len(body) > MAX_PAYLOAD_BYTES:
            return JSONResponse(
                status_code=413,
                content=error_body(
                    f"Request body exceeds {MAX_PAYLOAD_BYTES} bytes.",
                    "payload_too_large",
                ),
            )

    return await call_next(request)


install_error_handlers(app)

app.include_router(sensor.router)
app.include_router(internal.router)
app.include_router(websocket_router)


@app.get("/", tags=["meta"])
def root():
    """One line about what this service is, plus the disclaimer.

    The disclaimer is not decoration: this API delivers screening data, and
    anything a user can read has to say it is not a diagnosis.
    """
    return {
        "service": "ECG telemetry API",
        "version": "2.0.0",
        "docs": "/docs",
        "notice": "Screening aid, not a medical diagnosis.",
    }


@app.get("/health", tags=["meta"])
def health():
    """Liveness probe used by the frontend and by docker compose."""
    return {"status": "ok", "service": "fastapi"}
