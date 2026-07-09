"""
Demo seed script (DS-6).

Idempotent and deterministic: safe to run repeatedly (docker compose run
api python scripts/seed_demo.py) -- existing rows are detected by a fixed
identity (email for users, idempotency_key prefix for transactions,
nickname for beneficiaries) and skipped/reused rather than duplicated.
random.seed(SEED) makes all generated amounts/dates/choices identical
across runs.

Scope decisions (documented here rather than silently assumed):

- 6 users: demo1..demo4 are KYC-approved with full activity (wallets,
  balances, beneficiaries, transactions). demo5 is KYC-pending, demo6 is
  KYC-flagged -- neither gets money-movement data, matching how real
  onboarding gates activity behind KYC (see auth.py::register,
  admin.py's approve/reject flow).

- Transaction categories use the real taxonomy from
  app/tasks/categorization_tasks.py (CATEGORIES), not invented names --
  this seed does NOT call the real categorize_transaction Celery task
  (that hits a live Groq endpoint and isn't deterministic); category is
  assigned directly from the seeded RNG instead.

- Wallet balances are set directly to fixed target amounts. The ~200
  generated transactions are independent, illustrative history for
  volume/category/date-spread purposes only -- they do NOT debit/credit
  wallet.balance and won't mathematically reconcile with it. This keeps
  the script simple, deterministic, and idempotent without needing to
  replay/reset a transaction ledger on every run. Confirmed acceptable
  for demo purposes.

- Transactions/top-ups are NOT routed through send_money() or the real
  top-up endpoint -- those involve fraud-score dispatch, Redis
  idempotency middleware, and (for top-up) a live gateway call, none of
  which belong in an offline seed script. Transaction rows are created
  directly via the ORM instead, which still satisfies "ORM/service layer
  only, no raw SQL" -- this is direct model construction, not raw SQL.

- Notifications: reuses the real notify() service for KYC status
  (mirrors admin.py's actual approve/flag code path) plus a small fixed
  sample of transaction-confirmation notifications -- not one per seeded
  transaction (200 notify() calls would be slow and would spam the
  redis-publish/email side effects notify() performs for a seed run).
"""
import sys
from pathlib import Path

# Standalone script invoked directly (python scripts/seed_demo.py, or
# docker compose run api python scripts/seed_demo.py) -- sys.path[0]
# defaults to this script's own directory, not backend/, so `app` isn't
# importable without this. No PYTHONPATH is set for the api service in
# docker-compose.yml, so this is required for both local and Docker runs.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncio
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

import app.models  # noqa: F401 -- registers most mapped classes so string-based
# relationship() references on User resolve correctly. UserSession isn't
# re-exported from app.models.__init__, so import it directly too.
from app.models.session import UserSession  # noqa: F401

from app.core.security import hash_password
from app.db.session import AsyncSessionLocal, engine
from app.models.beneficiary import Beneficiary, BeneficiaryType
from app.models.kyc_record import KYCRecord, KYCRecordStatus
from app.models.notification import NotificationType
from app.models.transaction import Transaction, TransactionCurrency, TransactionStatus
from app.models.user import KYCStatus, User, UserRole
from app.models.wallet import Wallet, WalletCurrency
from app.services.account_service import create_wallets_for_user
from app.services.notifications import notify
from app.tasks.categorization_tasks import CATEGORIES

SEED = 42
random.seed(SEED)

TRANSACTION_COUNT = 200
TRANSACTION_WINDOW_DAYS = 30
IDEMPOTENCY_PREFIX = "seed-demo-tx-"

# (label, email, phone, kyc_status, usd_balance)
DEMO_USERS = [
    ("Demo User One", "demo1@neobank.test", "+96170000001", "approved", Decimal("5000.00")),
    ("Demo User Two", "demo2@neobank.test", "+96170000002", "approved", Decimal("2500.00")),
    ("Demo User Three", "demo3@neobank.test", "+96170000003", "approved", Decimal("1000.00")),
    ("Demo User Four", "demo4@neobank.test", "+96170000004", "approved", Decimal("750.00")),
    ("Demo User Five", "demo5@neobank.test", "+96170000005", "pending", Decimal("0")),
    ("Demo User Six", "demo6@neobank.test", "+96170000006", "flagged", Decimal("0")),
]

DEMO_PASSCODE = "123456"

BENEFICIARY_TEMPLATES = [
    ("Mom", BeneficiaryType.MOBILE, "+96170111111"),
    ("Landlord", BeneficiaryType.IBAN, "LB62999900000001001901229114"),
]


async def _get_or_create_user(db, label, email, phone, kyc_status_str) -> tuple[User, bool]:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is not None:
        return user, False

    kyc_status = KYCStatus(kyc_status_str)
    user = User(
        full_name=label,
        email=email,
        phone=phone,
        password_hash=hash_password("DemoPass123"),
        passcode_hash=hash_password(DEMO_PASSCODE),
        kyc_status=kyc_status,
        role=UserRole.customer,
    )
    db.add(user)
    await db.flush()
    return user, True


async def _get_or_create_kyc_record(db, user: User, status_str: str) -> KYCRecord:
    result = await db.execute(select(KYCRecord).where(KYCRecord.user_id == user.id))
    record = result.scalar_one_or_none()
    status = KYCRecordStatus(status_str)

    if record is not None:
        record.status = status
        return record

    record = KYCRecord(
        user_id=user.id,
        status=status,
        match_score=0.97 if status == KYCRecordStatus.approved else None,
        liveness_score=0.95 if status == KYCRecordStatus.approved else None,
        rejection_reason="Manual review required" if status == KYCRecordStatus.flagged else None,
        reviewed_at=datetime.now(timezone.utc) if status != KYCRecordStatus.pending else None,
    )
    db.add(record)
    await db.flush()
    return record


async def _get_or_create_beneficiaries(db, user: User) -> None:
    for nickname, ben_type, value in BENEFICIARY_TEMPLATES:
        result = await db.execute(
            select(Beneficiary).where(
                Beneficiary.user_id == user.id,
                Beneficiary.nickname == nickname,
            )
        )
        if result.scalar_one_or_none() is not None:
            continue
        db.add(
            Beneficiary(
                user_id=user.id,
                nickname=nickname,
                type=ben_type,
                value=value,
            )
        )
    await db.flush()


async def _seed_transactions(db, approved_users: list[User]) -> None:
    result = await db.execute(
        select(Transaction.idempotency_key).where(
            Transaction.idempotency_key.like(f"{IDEMPOTENCY_PREFIX}%")
        )
    )
    existing_keys = {row[0] for row in result.all()}

    if len(existing_keys) >= TRANSACTION_COUNT:
        return

    now = datetime.now(timezone.utc)
    to_create = TRANSACTION_COUNT - len(existing_keys)

    for i in range(to_create):
        idx = len(existing_keys) + i
        key = f"{IDEMPOTENCY_PREFIX}{idx:04d}"
        if key in existing_keys:
            continue

        sender = random.choice(approved_users)
        receiver = random.choice([u for u in approved_users if u.id != sender.id])
        category = random.choice(CATEGORIES)
        amount = Decimal(random.randrange(500, 15000)) / Decimal("100")
        days_ago = random.uniform(0, TRANSACTION_WINDOW_DAYS)
        created_at = now - timedelta(days=days_ago)

        db.add(
            Transaction(
                sender_id=sender.id,
                receiver_id=receiver.id,
                amount=amount,
                currency=TransactionCurrency.USD,
                category=category,
                status=TransactionStatus.completed,
                idempotency_key=key,
                created_at=created_at,
            )
        )

    await db.flush()


async def _seed_kyc_notification(db, user: User, status: str) -> None:
    notification_type = {
        "approved": NotificationType.KYC_APPROVED,
        "flagged": NotificationType.KYC_FLAGGED,
    }.get(status)
    if notification_type is None:
        return

    from app.models.notification import Notification

    result = await db.execute(
        select(Notification).where(
            Notification.user_id == user.id,
            Notification.type == notification_type,
        )
    )
    if result.scalar_one_or_none() is not None:
        return

    await notify(
        user_id=user.id,
        notification_type=notification_type,
        metadata={"full_name": user.full_name},
        db=db,
    )


async def main() -> None:
    async with AsyncSessionLocal() as db:
        approved_users: list[User] = []

        for label, email, phone, kyc_status_str, usd_balance in DEMO_USERS:
            user, created = await _get_or_create_user(db, label, email, phone, kyc_status_str)
            await _get_or_create_kyc_record(db, user, kyc_status_str)

            await create_wallets_for_user(user.id, db)

            if kyc_status_str == "approved":
                result = await db.execute(
                    select(Wallet).where(
                        Wallet.user_id == user.id,
                        Wallet.currency == WalletCurrency.USD,
                    )
                )
                usd_wallet = result.scalar_one()
                usd_wallet.balance = usd_balance

                await _get_or_create_beneficiaries(db, user)
                approved_users.append(user)

            await _seed_kyc_notification(db, user, kyc_status_str)

            print(f"{'Created' if created else 'Reused'}: {email} ({kyc_status_str})")

        await db.commit()

        await _seed_transactions(db, approved_users)
        await db.commit()

        print(f"Seed complete. {len(approved_users)} approved users with activity.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())


