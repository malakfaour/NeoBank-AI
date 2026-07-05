import time

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_async_db
from app.models.chatbot_log import ChatbotLog
from app.schemas.chatbot import ChatbotMessageRequest, ChatbotMessageResponse
from app.schemas.user import CurrentUser
from app.services.chatbot_intent import classify_intent
from app.services.chatbot_service import get_chatbot_response

router = APIRouter()

_TRANSFER_CONFIRMATION_THRESHOLD = 0.8


@router.post(
    "/message",
    response_model=ChatbotMessageResponse,
    summary="Send a message to the chatbot",
)
async def send_chatbot_message(
    body: ChatbotMessageRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> ChatbotMessageResponse:
    start = time.monotonic()
    classification = await classify_intent(body.message)
    latency_ms = int((time.monotonic() - start) * 1000)

    db.add(
        ChatbotLog(
            user_id=int(current_user.id),
            intent=classification.intent,
            confidence=classification.confidence,
            latency_ms=latency_ms,
        )
    )
    await db.commit()

    confirmation_required = (
        classification.intent == "TRANSFER_INTENT"
        and classification.confidence > _TRANSFER_CONFIRMATION_THRESHOLD
    )

    if confirmation_required:
        response_text = (
            "It looks like you want to make a transfer. Please confirm the "
            "details before I proceed."
        )
    else:
        response_text = get_chatbot_response(body.message)

    return ChatbotMessageResponse(
        message=body.message,
        response=response_text,
        intent=classification.intent,
        confidence=classification.confidence,
        original_message=body.message,
        confirmation_required=confirmation_required,
    )