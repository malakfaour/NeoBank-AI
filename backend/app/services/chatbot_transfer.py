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

_IBAN_PATTERN = re.compile(r"(?<![A-Za-z0-9])LB[A-Za-z0-9]{22}(?![A-Za-z0-9])", re.IGNORECASE)
_PHONE_PATTERN = re.compile(r"\+?\d[\d\s\-]{6,}\d")
_CURRENCY_PATTERN = re.compile(
    r"(?<![A-Za-z])(?P<currency>USD|LBP|USDT|\$|LL|L\.L\.|lira|dollar|dollars)(?![A-Za-z])",
    re.IGNORECASE,
)
_AMOUNT_PATTERN = re.compile(r"(?<![\d+])(?P<amount>\d+(?:[\.,]\d+)?)(?![\d])")


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


@dataclass(frozen=True)
class ChatbotPartialTransferDraft:
    amount: Decimal | None = None
    currency: str | None = None
    method: str | None = None
    recipient: str | None = None

    def merge(
        self, other: "ChatbotPartialTransferDraft"
    ) -> "ChatbotPartialTransferDraft":
        return ChatbotPartialTransferDraft(
            amount=other.amount if other.amount is not None else self.amount,
            currency=(
                other.currency if other.currency is not None else self.currency
            ),
            method=other.method if other.method is not None else self.method,
            recipient=(
                other.recipient if other.recipient is not None else self.recipient
            ),
        )

    def has_fields(self) -> bool:
        return any(
            value is not None
            for value in (self.amount, self.currency, self.method, self.recipient)
        )

    def missing_fields(self) -> list[str]:
        missing = []
        if self.amount is None:
            missing.append("amount")
        if self.currency is None:
            missing.append("currency")
        if self.method is None or self.recipient is None:
            missing.append("recipient")
        return missing

    def supplies_any(self, fields: list[str]) -> bool:
        return (
            ("amount" in fields and self.amount is not None)
            or ("currency" in fields and self.currency is not None)
            or (
                "recipient" in fields
                and self.method is not None
                and self.recipient is not None
            )
        )

    def to_complete_draft(self) -> ChatbotTransferDraft | None:
        if self.missing_fields() or self.currency not in {"USD", "LBP", "USDT"}:
            return None

        return ChatbotTransferDraft(
            method=str(self.method),
            recipient=str(self.recipient),
            amount=self.amount,
            currency=self.currency,
        )

    def to_storage_payload(self, *, user_id: int) -> dict[str, str | int]:
        payload: dict[str, str | int] = {
            "type": "incomplete_transfer",
            "user_id": user_id,
        }
        if self.amount is not None:
            payload["amount"] = str(self.amount)
        if self.currency is not None:
            payload["currency"] = self.currency
        if self.method is not None:
            payload["method"] = self.method
        if self.recipient is not None:
            payload["recipient"] = self.recipient
        return payload

    @classmethod
    def from_storage_payload(cls, payload: dict[str, Any]) -> "ChatbotPartialTransferDraft":
        raw_amount = payload.get("amount")
        return cls(
            amount=Decimal(str(raw_amount)) if raw_amount is not None else None,
            currency=payload.get("currency"),
            method=payload.get("method"),
            recipient=payload.get("recipient"),
        )


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
        normalized = normalize_lebanese_phone(raw_phone)
        if normalized is not None:
            return "mobile", normalized

    return None


def normalize_lebanese_phone(value: str) -> str | None:
    """Apply the same Lebanese mobile normalization rules as registration."""
    digits = re.sub(r"\D", "", value)
    if digits.startswith("00961"):
        digits = digits[5:]
    elif digits.startswith("961"):
        digits = digits[3:]
    if digits.startswith("0"):
        digits = digits[1:]
    if re.fullmatch(r"(?:3\d{6}|(?:70|71|76|78|79|81)\d{6})", digits):
        return f"+961{digits}"
    return None


def recipient_validation_error(message: str) -> str | None:
    """Return feedback only for input that clearly looks like a recipient."""
    value = message.strip()
    compact = re.sub(r"[\s-]", "", value)
    if compact.upper().startswith("LB"):
        if not _IBAN_PATTERN.fullmatch(compact):
            return (
                "That IBAN is invalid. A Lebanese IBAN must start with LB "
                "and contain 24 characters. Please check it and try again."
            )
        return None
    if re.fullmatch(r"[+\d][\d\s-]+", value) and (
        value.startswith("+") or compact.startswith(("00961", "961", "0"))
    ):
        if normalize_lebanese_phone(value) is None:
            return (
                "That phone number is invalid. Please use a valid Lebanese "
                "mobile number, for example +96170111222."
            )
    return None


def extract_partial_transfer_draft(message: str) -> ChatbotPartialTransferDraft:
    amount_currency = _extract_amount_currency(message)
    recipient = _extract_recipient(message)

    amount = amount_currency[0] if amount_currency is not None else None
    currency = amount_currency[1] if amount_currency is not None else None

    if currency is None:
        currency_match = _CURRENCY_PATTERN.search(message)
        if currency_match is not None:
            currency = _normalize_currency(currency_match.group("currency"))

    if amount is None:
        recipient_spans = [
            match.span()
            for pattern in (_IBAN_PATTERN, _PHONE_PATTERN)
            for match in pattern.finditer(message)
        ]
        for amount_match in _AMOUNT_PATTERN.finditer(message):
            if any(
                start <= amount_match.start() and amount_match.end() <= end
                for start, end in recipient_spans
            ):
                continue
            try:
                candidate = Decimal(amount_match.group("amount").replace(",", "."))
            except InvalidOperation:
                continue
            if candidate > 0:
                amount = candidate
                break

    method = recipient[0] if recipient is not None else None
    recipient_value = recipient[1] if recipient is not None else None
    return ChatbotPartialTransferDraft(
        amount=amount,
        currency=currency,
        method=method,
        recipient=recipient_value,
    )


def extract_transfer_draft(message: str) -> ChatbotTransferDraft | None:
    return extract_partial_transfer_draft(message).to_complete_draft()


def build_incomplete_transfer_reply(draft: ChatbotPartialTransferDraft) -> str:
    missing = draft.missing_fields()
    known = []
    if draft.amount is not None:
        known.append(str(draft.amount))
    if draft.currency is not None:
        known.append(draft.currency)
    prefix = f"Got it — {' '.join(known)}. " if known else ""

    if missing == ["recipient"]:
        return prefix + "Who should I send it to? Please provide a phone number or IBAN."
    if missing == ["currency"]:
        return prefix + "Which currency should I use: USD, LBP, or USDT?"
    if missing == ["amount"]:
        return prefix + "How much should I send?"

    labels = {
        "amount": "the amount",
        "currency": "the currency (USD, LBP, or USDT)",
        "recipient": "the recipient phone number or IBAN",
    }
    requested = [labels[field] for field in missing]
    if len(requested) == 2:
        request_text = " and ".join(requested)
    else:
        request_text = ", ".join(requested[:-1]) + f", and {requested[-1]}"
    return prefix + f"Please provide {request_text}."
