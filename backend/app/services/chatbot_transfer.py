import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

CONFIRM_WORDS = {"confirm", "yes", "y", "ok", "okay", "proceed", "send"}
CANCEL_WORDS = {"cancel", "stop", "discard", "no", "nevermind", "never mind"}

_AMOUNT_CURRENCY_PATTERNS = [
    re.compile(
        r"(?P<amount>\d+(?:[\.,]\d+)?)\s*(?P<currency>USD|LBP|USDT|\$|LL|L\.L\.|lira|dollar|dollars)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?P<currency>USD|LBP|USDT|\$|LL|L\.L\.|lira|dollar|dollars)\s*(?P<amount>\d+(?:[\.,]\d+)?)",
        re.IGNORECASE,
    ),
]

_IBAN_PATTERN = re.compile(r"LB[A-Za-z0-9]{26}", re.IGNORECASE)
_PHONE_PATTERN = re.compile(r"\+?\d[\d\s\-]{6,}\d")


@dataclass(frozen=True)
class ChatbotTransferDraft:
    method: str
    recipient: str
    amount: Decimal
    currency: str

    def to_pending_action(
        self, *, user_id: int, idempotency_key: str
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": "transfer",
            "method": self.method,
            "recipient": self.recipient,
            "amount": str(self.amount),
            "currency": self.currency,
            "user_id": user_id,
            "idempotency_key": idempotency_key,
        }

        if self.method == "mobile":
            payload["receiver_phone"] = self.recipient
        else:
            payload["receiver_iban"] = self.recipient

        return payload

    def to_response_payload(self) -> dict[str, str]:
        return {
            "type": "transfer",
            "method": self.method,
            "recipient": self.recipient,
            "amount": str(self.amount),
            "currency": self.currency,
        }


def is_confirm_message(message: str) -> bool:
    return message.strip().lower() in CONFIRM_WORDS


def is_cancel_message(message: str) -> bool:
    return message.strip().lower() in CANCEL_WORDS


def build_transfer_confirmation_reply(draft: ChatbotTransferDraft) -> str:
    return (
        "Please confirm this transfer: "
        f"{draft.amount} {draft.currency} to {draft.recipient}. "
        "To proceed, verify your passcode and send confirm with the action token."
    )


def _normalize_currency(raw_currency: str) -> str:
    value = raw_currency.strip().upper().replace(".", "")

    if value in {"$", "DOLLAR", "DOLLARS"}:
        return "USD"

    if value in {"LL", "LIRA"}:
        return "LBP"

    return value


def _extract_amount_currency(message: str) -> tuple[Decimal, str] | None:
    for pattern in _AMOUNT_CURRENCY_PATTERNS:
        match = pattern.search(message)

        if match is None:
            continue

        raw_amount = match.group("amount").replace(",", ".")
        currency = _normalize_currency(match.group("currency"))

        try:
            amount = Decimal(raw_amount)
        except InvalidOperation:
            return None

        if amount <= 0:
            return None

        return amount, currency

    return None


def _extract_recipient(message: str) -> tuple[str, str] | None:
    iban_match = _IBAN_PATTERN.search(message)
    if iban_match is not None:
        return "iban", iban_match.group(0).upper()

    for match in _PHONE_PATTERN.finditer(message):
        raw_phone = match.group(0)
        digits = re.sub(r"\D", "", raw_phone)

        if len(digits) < 7:
            continue

        normalized = "+" + digits if raw_phone.strip().startswith("+") else digits
        return "mobile", normalized

    return None


def extract_transfer_draft(message: str) -> ChatbotTransferDraft | None:
    amount_currency = _extract_amount_currency(message)
    recipient = _extract_recipient(message)

    if amount_currency is None or recipient is None:
        return None

    amount, currency = amount_currency
    method, recipient_value = recipient

    if currency not in {"USD", "LBP", "USDT"}:
        return None

    return ChatbotTransferDraft(
        method=method,
        recipient=recipient_value,
        amount=amount,
        currency=currency,
    )
