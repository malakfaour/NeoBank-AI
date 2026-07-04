import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.auth import router as auth_router
from app.api.passcode import router as passcode_router
from app.api.sessions import router as sessions_router
from app.api.chatbot import router as chatbot_router
from app.api.kyc import router as kyc_router
from app.api.v1.endpoints.exchange import router as exchange_router
from app.api.v1.endpoints.accounts import router as accounts_router
from app.api.v1.endpoints.notifications import router as notifications_router
from app.api.v1.endpoints.transactions import router as transactions_router
from app.api.v1.endpoints.transfer import router as transfer_router
from app.api.v1.endpoints.beneficiaries import router as beneficiaries_router
from app.api.v1.endpoints.admin import router as admin_router
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

app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(passcode_router, prefix="/auth/passcode", tags=["passcode"])
app.include_router(sessions_router, prefix="/auth/sessions", tags=["sessions"])
app.include_router(kyc_router, prefix="/kyc", tags=["kyc"])
app.include_router(chatbot_router, prefix="/chatbot", tags=["chatbot"])
app.include_router(exchange_router)
app.include_router(notifications_router)
app.include_router(transactions_router)
app.include_router(transfer_router)
app.include_router(accounts_router, prefix="/api/v1")
app.include_router(beneficiaries_router)
app.include_router(admin_router)


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