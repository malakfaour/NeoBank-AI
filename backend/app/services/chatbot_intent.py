import json
import logging
from typing import Literal

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import settings

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3-8b"

IntentLabel = Literal[
    "BALANCE_QUERY",
    "TRANSACTION_QUERY",
    "EXCHANGE_QUERY",
    "TRANSFER_INTENT",
    "GENERAL",
]

_VALID_INTENTS = {
    "BALANCE_QUERY",
    "TRANSACTION_QUERY",
    "EXCHANGE_QUERY",
    "TRANSFER_INTENT",
    "GENERAL",
}


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
        return IntentClassification(intent="GENERAL", confidence=0.0)