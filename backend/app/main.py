import logging
import uuid

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.datastructures import MutableHeaders

from app.api.v1.router import router as v1_router
from app.core.config import settings
from app.core.logging_config import configure_logging
from app.core.redis import redis_client
from app.core.request_context import get_request_id, request_id_var

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
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "internal_error", "request_id": request_id},
        headers={"X-Request-ID": request_id},
    )


app.include_router(v1_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    try:
        await redis_client.ping()
        redis_status = "ok"
    except Exception:
        redis_status = "unavailable"
    return {
        "status": "ok",
        "env": settings.APP_ENV,
        "redis": redis_status,
    }
