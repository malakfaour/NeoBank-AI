import asyncio
import logging
import uuid

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.datastructures import MutableHeaders

from app.api.v1.router import router as v1_router
from app.celery_app import celery_app
from app.core.config import settings
from app.core.logging_config import configure_logging
from app.core.redis import redis_client
from app.core.request_context import get_request_id, request_id_var
from app.db.session import AsyncSessionLocal

configure_logging(settings.LOG_FORMAT)

logger = logging.getLogger("app")

app = FastAPI(
    title="NeoBank Lebanon API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RequestIDMiddleware:
    """
    DEVATTECH-122: assigns a UUID per request, makes it available to every
    log call during that request via request_id_var, and echoes it back
    as X-Request-ID.

    Implemented as a raw ASGI middleware (not @app.middleware("http")) --
    that decorator style uses Starlette's BaseHTTPMiddleware, which has a
    known bug where it re-raises exceptions even after a registered
    exception_handler already produced a response. A plain ASGI class
    doesn't have that problem.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        req_id = str(uuid.uuid4())
        token = request_id_var.set(req_id)

        response_started = False

        async def send_wrapper(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                headers = MutableHeaders(scope=message)
                headers.append("X-Request-ID", req_id)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            if response_started:
                raise
            logger.exception(
                "Unhandled exception on %s %s",
                scope.get("method", "<unknown>"),
                scope.get("path", "<unknown>"),
            )
            response = JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"error": "internal_error", "request_id": req_id},
                headers={"X-Request-ID": req_id},
            )
            await response(scope, receive, send)
        finally:
            request_id_var.reset(token)


app.add_middleware(RequestIDMiddleware)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    DEVATTECH-122: catches anything not already handled as an HTTPException.
    Logs the full exception server-side (with request_id automatically
    attached by the logging filter); returns only a generic error + the
    request_id to the client -- never a stack trace or exception message.
    """
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    request_id = get_request_id()
    response = JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "internal_error", "request_id": request_id},
    )
    if request_id:
        response.headers["X-Request-ID"] = request_id
    return response


app.include_router(v1_router, prefix="/api/v1")

@app.get("/health")
async def health_check():
    try:
        await redis_client.ping()
        redis_status = "ok"
    except Exception:
        redis_status = "unavailable"

    beat_last_run_age = None

    try:
        last_run = await redis_client.get(
            "beat:last_run"
        )

        if last_run:
            from datetime import datetime, timezone

            if isinstance(last_run, bytes):
                last_run = last_run.decode("utf-8")

            timestamp = datetime.fromisoformat(
                last_run
            )

            beat_last_run_age = int(
                (
                    datetime.now(timezone.utc)
                    - timestamp
                ).total_seconds()
            )

    except Exception:
        beat_last_run_age = None

    return {
        "status": "ok",
        "env": settings.APP_ENV,
        "redis": redis_status,
<<<<<<< HEAD
    }


@app.get("/health/ready")
async def readiness_check():
    """
    DEVATTECH-123 / SP3-704: readiness probe -- checks every dependency
    the app actually needs to serve traffic (DB, Redis, Celery workers).

    Unlike /health (liveness, kept deliberately cheap -- no DB call),
    this does real work and is meant for orchestrator readiness checks,
    not high-frequency polling.
    """
    checks: dict[str, str] = {}

    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        logger.exception("Readiness check: database unavailable")
        checks["database"] = "unavailable"

    try:
        await redis_client.ping()
        checks["redis"] = "ok"
    except Exception:
        logger.exception("Readiness check: redis unavailable")
        checks["redis"] = "unavailable"

    try:
        # control.ping() is a blocking call (kombu/broker round-trip) --
        # run it off the event loop so one slow/dead worker can't stall
        # every concurrent request being handled by this process.
        responses = await asyncio.to_thread(celery_app.control.ping, timeout=2.0)
        checks["celery"] = "ok" if responses else "unavailable"
    except Exception:
        logger.exception("Readiness check: celery unavailable")
        checks["celery"] = "unavailable"

    all_ok = all(v == "ok" for v in checks.values())
    return JSONResponse(
        status_code=status.HTTP_200_OK if all_ok else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "ready" if all_ok else "not_ready", "checks": checks},
    )
=======
        "beat_last_run_age": beat_last_run_age,
    }
>>>>>>> 67cd178 (fix(exchange): address PR review comments)
