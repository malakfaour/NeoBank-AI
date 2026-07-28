import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.account_service import get_user_balances
from app.services.exchange_cache import (
    fetch_exchange_rates,
    get_cached_exchange_rates_with_age,
    set_cached_exchange_rates,
)
from app.services.transaction_query_service import get_recent_transactions_for_user

SUPPORTED_CURRENCIES = {"USD", "LBP", "USDT"}
APPLICATION_TIMEZONE = ZoneInfo("Asia/Beirut")
OUT_OF_SCOPE_REPLY = (
    "I can only assist with NeoBank services such as balances, "
    "transactions, transfers, and exchange rates."
)
EXCHANGE_UNAVAILABLE_REPLY = (
    "The current exchange rate is unavailable. Please try again later."
)


def _money(value: object, currency: str) -> str:
    amount = Decimal(str(value))
    if currency == "USD":
        return f"${amount.quantize(Decimal('0.01'))}"
    if currency == "LBP":
        return f"{amount.quantize(Decimal('1')):,} LBP"
    return f"{amount.quantize(Decimal('0.01'))} {currency}"


def _rate(value: Decimal) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


async def balance_reply(*, user_id: int, db: AsyncSession) -> str:
    payload = await get_user_balances(user_id=user_id, db=db)
    wallets = payload.get("balances", []) if payload else []
    if not wallets:
        return "You do not have any wallets yet."
    lines = [
        f"- {wallet['currency']}: {_money(wallet['balance'], wallet['currency'])}"
        for wallet in wallets
    ]
    return "Your wallet balances are:\n" + "\n".join(lines)


def _transaction_line(item: dict) -> str:
    kind = {
        "send": "Sent",
        "receive": "Received",
        "top_up": "Top-up",
        "exchange": "Exchange",
        "fee": "Fee",
    }.get(str(item.get("type")), str(item.get("type", "Transaction")).title())
    counterparty = item.get("counterparty_name") or item.get("category") or "NeoBank"
    timestamp = _format_transaction_timestamp(item.get("created_at"))
    return (
        f"{kind}: {_money(item['amount'], item['currency'])} — "
        f"{counterparty} — {timestamp}"
    )


def _format_transaction_timestamp(value: object) -> str:
    if not value:
        return "timestamp unavailable"
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        local = parsed.astimezone(APPLICATION_TIMEZONE)
        hour = local.strftime("%I").lstrip("0")
        return f"{local:%d %b %Y}, {hour}:{local:%M} {local:%p}"
    except (TypeError, ValueError):
        return "timestamp unavailable"


async def transaction_reply(
    *, user_id: int, db: AsyncSession, mode: str
) -> str:
    # Always query the database for the current request; conversation history
    # is never a financial-data source.
    items = await get_recent_transactions_for_user(user_id=user_id, db=db, limit=20)
    if mode == "last_spending":
        items = [item for item in items if item["type"] in {"send", "fee", "exchange"}]
        empty = "You have no outgoing transactions."
    else:
        empty = "You have no matching transactions."
    if not items:
        return empty
    selected = items[:5] if mode == "recent" else items[:1]
    heading = "Your recent transactions are:" if mode == "recent" else "Your latest transaction is:"
    return heading + "\n" + "\n".join(f"- {_transaction_line(item)}" for item in selected)


def parse_exchange_request(message: str) -> tuple[Decimal | None, str, str] | None:
    pair = re.search(
        r"(?:(?:convert|exchange)\s+)?(?:(\d+(?:[.,]\d+)?)\s*)?"
        r"\b(USD|LBP|USDT)\b\s*(?:to|into|/|-)\s*\b(USD|LBP|USDT)\b",
        message,
        re.I,
    )
    if not pair:
        return None
    try:
        amount = Decimal(pair.group(1).replace(",", ".")) if pair.group(1) else None
    except InvalidOperation:
        return None
    return amount, pair.group(2).upper(), pair.group(3).upper()


async def exchange_reply(message: str) -> str:
    parsed = parse_exchange_request(message)
    if parsed is None:
        return "Please provide a currency pair, for example USD to LBP."
    amount, source, target = parsed
    if source == target or source not in SUPPORTED_CURRENCIES or target not in SUPPORTED_CURRENCIES:
        return f"The exchange pair {source} to {target} is not supported."
    try:
        rates, age = await get_cached_exchange_rates_with_age()
        if rates is None:
            rates = await fetch_exchange_rates()
            await set_cached_exchange_rates(rates)
            age = 0
        rate = rates.get((source, target))
    except Exception:
        return EXCHANGE_UNAVAILABLE_REPLY
    if rate is None:
        return f"The exchange pair {source} to {target} is not currently available."
    rate_text = _rate(rate)
    if amount is None:
        return f"Current exchange rate: 1 {source} = {rate_text} {target}."
    converted = (amount * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return (
        f"Conversion:\n- Source: {_money(amount, source)}\n"
        f"- Rate: 1 {source} = {rate_text} {target}\n"
        f"- Converted amount: {_money(converted, target)}\n"
        f"- Rate age: {age or 0} seconds"
    )
