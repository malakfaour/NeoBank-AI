from typing import Any

from pydantic import BaseModel, Field

from app.schemas.transfer import TransferReceipt
from app.services.chatbot_intent import IntentLabel


class ChatbotMessageRequest(BaseModel):
    session_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
    )

    message: str = Field(
        ...,
        min_length=1,
        max_length=2000,
    )


class ChatbotMessageResponse(BaseModel):
    reply: str
    session_id: str
    intent: IntentLabel
    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )
    confirmation_required: bool = False
    pending_action: dict[str, str] | None = None
    transfer_receipt: TransferReceipt | None = None


class ChatbotHistoryResponse(BaseModel):
    session_id: str
    messages: list[dict[str, Any]]
