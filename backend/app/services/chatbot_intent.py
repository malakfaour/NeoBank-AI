from __future__ import annotations

import json
import logging
import re
from typing import Literal

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import settings

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3-8b"

IntentLabel = Literal[
    "GREETING",
    "BALANCE_QUERY",
    "LAST_TRANSACTION_QUERY",
    "RECENT_TRANSACTIONS_QUERY",
    "LAST_SPENDING_QUERY",
    "EXCHANGE_RATE_QUERY",
    "CURRENCY_CONVERSION",
    "TRANSACTION_QUERY",
    "EXCHANGE_QUERY",
    "TRANSFER_INTENT",
    "OUT_OF_SCOPE",
    "GENERAL",
]

_VALID_INTENTS = {
    "GREETING",
    "BALANCE_QUERY",
    "LAST_TRANSACTION_QUERY",
    "RECENT_TRANSACTIONS_QUERY",
    "LAST_SPENDING_QUERY",
    "EXCHANGE_RATE_QUERY",
    "CURRENCY_CONVERSION",
    "TRANSACTION_QUERY",
    "EXCHANGE_QUERY",
    "TRANSFER_INTENT",
    "OUT_OF_SCOPE",
    "GENERAL",
}

_GREETING_RE = re.compile(
    r"^\s*(hi|hello|hey|good\s+(morning|afternoon|evening))(?:\s+there)?[\s!.?]*$",
    re.I,
)
_BALANCE_RE = re.compile(r"\b(balance|wallet balance|money do i have|funds)\b", re.I)
_TRANSFER_RE = re.compile(r"\b(transfer|send|pay)\b.*\b(USD|LBP|USDT|\$|lira|dollars?)\b", re.I)
_CONVERSION_RE = re.compile(
    r"\b(convert|exchange)\b.*\d+(?:[.,]\d+)?\s*(USD|LBP|USDT)\b.*\b(to|into)\s*(USD|LBP|USDT)\b",
    re.I,
)
_RATE_RE = re.compile(r"\b(USD|LBP|USDT)\b\s*(?:to|/|-)\s*\b(USD|LBP|USDT)\b", re.I)
_LAST_SPENDING_RE = re.compile(
    r"(?:\b(last|latest)\b.*\b(spend|spent|spending|purchase|debit)\b"
    r"|\b(spend|spent|spending|purchase|debit)\b.*\b(last|latest)\b)",
    re.I,
)
_LAST_TRANSACTION_RE = re.compile(r"\b(last|latest)\b.*\btransaction\b", re.I)
_RECENT_TRANSACTIONS_RE = re.compile(r"\b(recent|last)\b.*\btransactions\b|\btransaction history\b", re.I)
_OUT_OF_SCOPE_RE = re.compile(
    r"\b(world cup|joke|python code|write code|weather|president|ignore previous|system prompt)\b",
    re.I,
)


def classify_supported_intent(message: str) -> IntentClassification | None:
    """Deterministically gate supported intents before any model is called."""
    if _GREETING_RE.search(message):
        return IntentClassification(intent="GREETING", confidence=1.0)
    if _OUT_OF_SCOPE_RE.search(message):
        return IntentClassification(intent="OUT_OF_SCOPE", confidence=1.0)
    if _TRANSFER_RE.search(message):
        return IntentClassification(intent="TRANSFER_INTENT", confidence=1.0)
    if _CONVERSION_RE.search(message):
        return IntentClassification(intent="CURRENCY_CONVERSION", confidence=1.0)
    if _RATE_RE.search(message):
        return IntentClassification(intent="EXCHANGE_RATE_QUERY", confidence=1.0)
    if _LAST_SPENDING_RE.search(message):
        return IntentClassification(intent="LAST_SPENDING_QUERY", confidence=1.0)
    if _LAST_TRANSACTION_RE.search(message):
        return IntentClassification(intent="LAST_TRANSACTION_QUERY", confidence=1.0)
    if _RECENT_TRANSACTIONS_RE.search(message):
        return IntentClassification(intent="RECENT_TRANSACTIONS_QUERY", confidence=1.0)
    if _BALANCE_RE.search(message):
        return IntentClassification(intent="BALANCE_QUERY", confidence=1.0)
    return None


class IntentClassification(BaseModel):
    """
    Shared contract for chatbot intent classification (NBL-712).

    Consumed by POST /chatbot/message and by M5's chatbot agent.
    Single owner: this module. Do not fork a second implementation --
    import classify_intent() instead of re-calling Groq elsewhere.
    """

    intent: IntentLabel
    confidence: float


_SYSTEM_PROMPT = (
    "You are an intent classifier for a banking chatbot. Classify the "
    "user's message into exactly one of: BALANCE_QUERY, TRANSACTION_QUERY, "
    "EXCHANGE_QUERY, TRANSFER_INTENT, GENERAL. Respond with ONLY a JSON "
    'object of the form {"intent": "<LABEL>", "confidence": <0.0-1.0>}. '
    "No prose, no markdown fences."
)


async def classify_intent(message: str) -> IntentClassification:
    """
    Classify a chatbot message's intent via Groq (llama-3-8b, max 150 tokens).

    Best-effort: on any network error, bad response shape, or invalid
    label, falls back to IntentClassification(intent="GENERAL",
    confidence=0.0) rather than raising -- classification must never
    break the chat reply flow.
    """
    deterministic = classify_supported_intent(message)
    if deterministic is not None:
        return deterministic

    payload = {
        "model": GROQ_MODEL,
        "max_tokens": 150,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ],
    }
    headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(GROQ_API_URL, json=payload, headers=headers)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        result = IntentClassification(
            intent=parsed["intent"],
            confidence=float(parsed["confidence"]),
        )
        if result.intent not in _VALID_INTENTS:
            raise ValueError(f"Unexpected intent label: {result.intent}")
        return result
    except (httpx.HTTPError, KeyError, ValueError, json.JSONDecodeError, ValidationError) as exc:
        logger.warning(f"Intent classification failed, defaulting to GENERAL: {exc}")
        return IntentClassification(intent="OUT_OF_SCOPE", confidence=1.0)
