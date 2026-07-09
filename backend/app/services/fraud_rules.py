"""
DEVATTECH-87: rule-based fraud fallback layer.

Deterministic checks that run in addition to ML scoring (Isolation Forest /
XGBoost, see fraud_scoring.py). Both signals are independent -- a
transaction can be ML-flagged, rule-flagged, both, or neither. This module
only computes rule results; the caller (send_money() in transactions.py)
is responsible for merging them into transaction.status and audit metadata.

Rule 4 (currency mismatch) is a hard reject, not a flag -- see docstring
on check_currency_match() for why it's currently unreachable given how
send_money() selects the sender's wallet.

NOTE: this module uses AsyncSession throughout, matching the async
FastAPI request path in transactions.py (db: AsyncSession = Depends(get_db)).
Do not swap this back to sqlalchemy.orm.Session -- that's for the sync
Celery engine (see app/db/sync_session.py), a different code path.

DEVATTECH-106: rules 1-3's threshold/comparison logic previously existed
twice (once inline in check_fraud_rules, once inline in
check_fraud_rules_sync). It now exists once each, as the pure
_evaluate_rule_1/2/3 functions below -- no I/O, no db parameter, same
input always produces the same output. check_fraud_rules() and
check_fraud_rules_sync() are now thin wrappers: fetch one value via the
matching async/sync I/O helper, delegate the decision to the pure
function, short-circuit on the first trigger (unchanged from before --
this avoids querying for rules 2/3 once rule 1 has already fired, same
as the original implementation). The I/O helper functions themselves
(_get_rolling_average_spend/_sync, etc.) are NOT consolidated -- that
would require calling an async service from a sync Celery path (or vice
versa), which ENGINEERING_RULES.md Section 3 forbids. That duplication is
inherent to the async/sync split, not "rule logic" duplication.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.transaction import Transaction
from app.models.wallet import Wallet

ROLLING_WINDOW_DAYS = 30
ROLLING_MULTIPLIER = Decimal("5")
MULTI_RECIPIENT_WINDOW_MINUTES = 5
MULTI_RECIPIENT_THRESHOLD = 3
NEW_RECIPIENT_AMOUNT_THRESHOLD = Decimal("500")


@dataclass
class RuleCheckResult:
    triggered: bool
    rule_name: str | None


class CurrencyMismatchError(Exception):
    """Raised for rule 4. Caller (send_money) should catch this and return
    422 immediately, before the transfer commits -- this is a reject, not
    a flag, unlike rules 1-3."""

    def __init__(self, tx_currency: str, wallet_currency: str):
        self.tx_currency = tx_currency
        self.wallet_currency = wallet_currency
        super().__init__(
            f"Transaction currency {tx_currency!r} does not match "
            f"source wallet currency {wallet_currency!r}"
        )


def check_currency_match(tx_currency: str, source_wallet: Wallet) -> None:
    """
    Rule 4: transaction currency must match the source wallet's currency.
    Raises CurrencyMismatchError if not -- caller maps this to HTTP 422.

    NOTE: as of DEVATTECH-87, send_money() selects the sender's wallet by
    filtering Wallet.currency == payload.currency (see transactions.py),
    so tx_currency and wallet_currency are structurally guaranteed to
    match today -- this check cannot currently trigger. It's included
    per the ticket as a defensive guard against future code paths (e.g.
    a route that resolves wallet and currency independently). Flagged to
    the team; not removing it since it's cheap insurance, but don't expect
    it to ever fire under the current send_money() implementation.

    This function does not touch the DB, so it stays sync -- no await
    needed at the call site.
    """
    if tx_currency != source_wallet.currency.value:
        raise CurrencyMismatchError(tx_currency, source_wallet.currency.value)


def _evaluate_rule_1(amount: Decimal, rolling_avg: Decimal) -> RuleCheckResult | None:
    """
    Rule 1 -- amount > 5x sender's rolling 30-day average.
    Pure: given the same amount and rolling_avg, always returns the same
    result. Returns None (not RuleCheckResult(triggered=False, ...)) when
    the rule doesn't fire, so callers can tell "this rule didn't trigger"
    apart from "this is the final answer" and keep checking the next rule.
    """
    if rolling_avg > 0 and amount > (rolling_avg * ROLLING_MULTIPLIER):
        return RuleCheckResult(triggered=True, rule_name="excessive_amount_vs_average")
    return None


def _evaluate_rule_2(prior_recipient_count: int) -> RuleCheckResult | None:
    """
    Rule 2 -- >=3 distinct recipients within 5 minutes, INCLUDING the
    transaction currently being scored. prior_recipient_count excludes
    that transaction, so the threshold is checked as (threshold - 1):
    this transaction's receiver is what pushes the count to the real
    threshold.
    """
    if prior_recipient_count >= MULTI_RECIPIENT_THRESHOLD - 1:
        return RuleCheckResult(triggered=True, rule_name="rapid_multi_recipient")
    return None


def _evaluate_rule_3(is_new_recipient: bool, amount: Decimal) -> RuleCheckResult | None:
    """Rule 3 -- new recipient AND amount > $500."""
    if is_new_recipient and amount > NEW_RECIPIENT_AMOUNT_THRESHOLD:
        return RuleCheckResult(triggered=True, rule_name="new_recipient_high_amount")
    return None


async def _get_rolling_average_spend(
    db: AsyncSession, sender_id: int, now: datetime
) -> Decimal:
    """Sender's average transaction amount over the trailing 30 days."""
    window_start = now - timedelta(days=ROLLING_WINDOW_DAYS)
    result = await db.execute(
        select(func.avg(Transaction.amount)).where(
            Transaction.sender_id == sender_id,
            # NBL-411: exclude self-transfers (top-ups) from the spend average --
            # otherwise a large top-up inflates the baseline and Rule 1 stops
            # flagging genuinely large sends.
            Transaction.sender_id != Transaction.receiver_id,
            Transaction.created_at >= window_start,
            Transaction.created_at < now,
        )
    )
    avg = result.scalar_one_or_none()
    return Decimal(str(avg)) if avg is not None else Decimal("0")


async def _count_distinct_recipients_recent(
    db: AsyncSession, sender_id: int, now: datetime
) -> int:
    """
    Distinct recipients the sender transacted with in the preceding
    MULTI_RECIPIENT_WINDOW_MINUTES, NOT counting the transaction currently
    being scored (it's the (n+1)th event, checked separately below).
    """
    window_start = now - timedelta(minutes=MULTI_RECIPIENT_WINDOW_MINUTES)
    result = await db.execute(
        select(func.count(func.distinct(Transaction.receiver_id))).where(
            Transaction.sender_id == sender_id,
            # NBL-411: exclude self-transfers (top-ups) -- otherwise the user
            # counts as their own `recipient`, inflating this toward the
            # rapid-multi-recipient threshold.
            Transaction.sender_id != Transaction.receiver_id,
            Transaction.created_at >= window_start,
            Transaction.created_at < now,
        )
    )
    return result.scalar_one() or 0


async def _is_new_recipient(
    db: AsyncSession, sender_id: int, receiver_id: int, exclude_transaction_id: int
) -> bool:
    """True if sender has no prior transactions to this receiver, excluding
    the transaction currently being scored."""
    result = await db.execute(
        select(func.count())
        .select_from(Transaction)
        .where(
            Transaction.sender_id == sender_id,
            Transaction.receiver_id == receiver_id,
            Transaction.id != exclude_transaction_id,
        )
    )
    return (result.scalar_one() or 0) == 0


async def check_fraud_rules(db: AsyncSession, transaction: Transaction) -> RuleCheckResult:
    """
    Run rules 1-3 (flag-only) against an already-committed transaction.
    Rule 4 (reject) is NOT run here -- call check_currency_match()
    separately, before commit, since it needs to short-circuit the
    transfer rather than flag after the fact.

    Rules run independently; first triggered rule wins for rule_name.
    Order below is check priority, not severity -- all three are equally
    "flag for review," this just determines which name lands in metadata
    when multiple rules would have fired.

    Each rule's data is fetched only if needed: fetching stops at the
    first rule that triggers, same as before DEVATTECH-106 -- this is a
    thin wrapper around the pure _evaluate_rule_* functions, not a
    fetch-everything-then-decide function, specifically to preserve that
    short-circuit (avoids two unnecessary queries once rule 1 has fired).
    """
    now = transaction.created_at or datetime.utcnow()

    rolling_avg = await _get_rolling_average_spend(db, transaction.sender_id, now)
    result = _evaluate_rule_1(transaction.amount, rolling_avg)
    if result is not None:
        return result

    prior_recipient_count = await _count_distinct_recipients_recent(
        db, transaction.sender_id, now
    )
    result = _evaluate_rule_2(prior_recipient_count)
    if result is not None:
        return result

    is_new = await _is_new_recipient(
        db, transaction.sender_id, transaction.receiver_id, transaction.id
    )
    result = _evaluate_rule_3(is_new, transaction.amount)
    if result is not None:
        return result

    return RuleCheckResult(triggered=False, rule_name=None)


def _get_rolling_average_spend_sync(
    db: Session, sender_id: int, now: datetime
) -> Decimal:
    window_start = now - timedelta(days=ROLLING_WINDOW_DAYS)
    result = db.execute(
        select(func.avg(Transaction.amount)).where(
            Transaction.sender_id == sender_id,
            # NBL-411: exclude self-transfers (top-ups) from the spend average --
            # otherwise a large top-up inflates the baseline and Rule 1 stops
            # flagging genuinely large sends.
            Transaction.sender_id != Transaction.receiver_id,
            Transaction.created_at >= window_start,
            Transaction.created_at < now,
        )
    )
    avg = result.scalar_one_or_none()
    return Decimal(str(avg)) if avg is not None else Decimal("0")


def _count_distinct_recipients_recent_sync(
    db: Session, sender_id: int, now: datetime
) -> int:
    window_start = now - timedelta(minutes=MULTI_RECIPIENT_WINDOW_MINUTES)
    result = db.execute(
        select(func.count(func.distinct(Transaction.receiver_id))).where(
            Transaction.sender_id == sender_id,
            # NBL-411: exclude self-transfers (top-ups) -- otherwise the user
            # counts as their own `recipient`, inflating this toward the
            # rapid-multi-recipient threshold.
            Transaction.sender_id != Transaction.receiver_id,
            Transaction.created_at >= window_start,
            Transaction.created_at < now,
        )
    )
    return result.scalar_one() or 0


def _is_new_recipient_sync(
    db: Session, sender_id: int, receiver_id: int, exclude_transaction_id: int
) -> bool:
    result = db.execute(
        select(func.count())
        .select_from(Transaction)
        .where(
            Transaction.sender_id == sender_id,
            Transaction.receiver_id == receiver_id,
            Transaction.id != exclude_transaction_id,
        )
    )
    return (result.scalar_one() or 0) == 0


def check_fraud_rules_sync(db: Session, transaction: Transaction) -> RuleCheckResult:
    """
    Sync equivalent of check_fraud_rules() for Celery task sessions.
    Same short-circuit shape as the async version -- see its docstring.
    """
    now = transaction.created_at or datetime.utcnow()

    rolling_avg = _get_rolling_average_spend_sync(db, transaction.sender_id, now)
    result = _evaluate_rule_1(transaction.amount, rolling_avg)
    if result is not None:
        return result

    prior_recipient_count = _count_distinct_recipients_recent_sync(
        db, transaction.sender_id, now
    )
    result = _evaluate_rule_2(prior_recipient_count)
    if result is not None:
        return result

    is_new = _is_new_recipient_sync(
        db, transaction.sender_id, transaction.receiver_id, transaction.id
    )
    result = _evaluate_rule_3(is_new, transaction.amount)
    if result is not None:
        return result

    return RuleCheckResult(triggered=False, rule_name=None)
