import time

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_async_db
from app.models.chatbot_log import ChatbotLog
from app.schemas.chatbot import (
    ChatbotMessageRequest,
    ChatbotMessageResponse,
)
from app.schemas.user import CurrentUser
from app.services.chatbot_intent import classify_intent
from app.services.rate_limiter import check_rate_limit
from app.services.chatbot_service import (
    ChatSessionOwnershipError,
    get_chatbot_response,
    save_chat_turn,
)

router = APIRouter()

_TRANSFER_CONFIRMATION_THRESHOLD = 0.8


@router.post(
    "/message",
    response_model=ChatbotMessageResponse,
    summary="Send a message to the chatbot",
)
async def send_chatbot_message(
    request: Request,
    body: ChatbotMessageRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> ChatbotMessageResponse:
    await check_rate_limit(
        request,
        key_prefix="chatbot_message",
        max_requests=20,
        window_seconds=60,
    )
    user_id = int(current_user.id)
    start = time.monotonic()

    classification = await classify_intent(
        body.message
    )

    latency_ms = int(
        (time.monotonic() - start) * 1000
    )

    db.add(
        ChatbotLog(
            user_id=user_id,
            intent=classification.intent,
            confidence=classification.confidence,
            latency_ms=latency_ms,
        )
    )

    confirmation_required = (
        classification.intent == "TRANSFER_INTENT"
        and classification.confidence
        > _TRANSFER_CONFIRMATION_THRESHOLD
    )

    try:
        if confirmation_required:
            reply = (
                "It looks like you want to make a transfer. "
                "Please confirm the details before I proceed."
            )

            await save_chat_turn(
                db=db,
                user_id=user_id,
                session_id=body.session_id,
                message=body.message,
                reply=reply,
            )

        else:
            reply = await get_chatbot_response(
                message=body.message,
                session_id=body.session_id,
                user_id=user_id,
                db=db,
            )

    except ChatSessionOwnershipError as exc:
        await db.rollback()

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    return ChatbotMessageResponse(
        reply=reply,
        session_id=body.session_id,
        intent=classification.intent,
        confidence=classification.confidence,
        confirmation_required=confirmation_required,
    )