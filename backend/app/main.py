import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as v1_router
from app.core.config import settings
from app.core.redis import redis_client

logging.getLogger("app").setLevel(logging.WARNING)
logging.getLogger("app").addHandler(logging.StreamHandler())

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

# ONLY THIS ROUTER
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