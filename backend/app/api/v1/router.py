from fastapi import APIRouter

from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.passcode import router as passcode_router
from app.api.v1.endpoints.sessions import router as sessions_router
from app.api.v1.endpoints.chatbot import router as chatbot_router
from app.api.v1.endpoints.kyc import router as kyc_router
from app.api.v1.endpoints.exchange import router as exchange_router
from app.api.v1.endpoints.accounts import router as accounts_router
from app.api.v1.endpoints.notifications import router as notifications_router
from app.api.v1.endpoints.transactions import router as transactions_router
from app.api.v1.endpoints.transfer import router as transfer_router
from app.api.v1.endpoints.beneficiaries import router as beneficiaries_router
from app.api.v1.endpoints.admin import router as admin_router
from app.api.v1.endpoints.users import router as users_router


router = APIRouter()

# ---------------- AUTH ----------------
router.include_router(auth_router, prefix="/auth", tags=["auth"])
router.include_router(passcode_router, prefix="/auth/passcode", tags=["passcode"])
router.include_router(sessions_router, prefix="/auth/sessions", tags=["sessions"])

# ---------------- CORE FEATURES ----------------
router.include_router(kyc_router, prefix="/kyc", tags=["kyc"])
router.include_router(chatbot_router, prefix="/chatbot", tags=["chatbot"])
router.include_router(exchange_router, prefix="/exchange", tags=["exchange"])
router.include_router(accounts_router, prefix="/accounts", tags=["accounts"])
router.include_router(notifications_router, prefix="/notifications", tags=["notifications"])
router.include_router(transactions_router, prefix="/transactions", tags=["transactions"])
router.include_router(transfer_router, prefix="/transfer", tags=["transfer"])
router.include_router(beneficiaries_router, prefix="/beneficiaries", tags=["beneficiaries"])

# ---------------- ADMIN ----------------
router.include_router(admin_router, prefix="/admin", tags=["admin"])

# ---------------- USERS ----------------
router.include_router(users_router, prefix="/users", tags=["users"])