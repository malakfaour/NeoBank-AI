from fastapi import APIRouter

from app.api.v1.endpoints.biometric import router as biometric_router
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
from app.api.v1.endpoints.bills import router as bills_router
from app.api.v1.endpoints.admin import router as admin_router
from app.api.v1.endpoints.users import router as users_router

# Aggregate router for all v1 endpoints. Mounted once, at "/api/v1", in
# main.py -- individual routers are NOT mounted directly there anymore.
#
# Sub-prefixes here exactly mirror what main.py used to pass to
# include_router() for each router, so existing route shapes are
# preserved except for the added "/api/v1" segment:
#   auth       -> /api/v1/auth/...
#   passcode   -> /api/v1/auth/passcode/...
#   sessions   -> /api/v1/auth/sessions/...
#   kyc        -> /api/v1/kyc/...
#   chatbot    -> /api/v1/chatbot/...
#
# exchange, accounts, notifications, transactions, transfer,
# beneficiaries, bills, and admin already declare their own prefix via
# APIRouter(prefix=...) in their respective modules, so no prefix is
# passed here for those -- adding one would double it up.
router = APIRouter()

router.include_router(auth_router, prefix="/auth", tags=["auth"])
router.include_router(passcode_router, prefix="/auth/passcode", tags=["passcode"])
router.include_router(biometric_router, prefix="/auth/biometric", tags=["biometric"])
router.include_router(sessions_router, prefix="/auth/sessions", tags=["sessions"])
router.include_router(kyc_router, prefix="/kyc", tags=["kyc"])
router.include_router(chatbot_router, prefix="/chatbot", tags=["chatbot"])
router.include_router(exchange_router)
router.include_router(accounts_router)
router.include_router(notifications_router)
router.include_router(transactions_router)
router.include_router(transfer_router)
router.include_router(beneficiaries_router)
router.include_router(bills_router)
router.include_router(admin_router)
router.include_router(users_router, prefix="/users", tags=["users"])