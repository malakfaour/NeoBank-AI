import time
from decimal import Decimal
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Request,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.redis import (
    consume_action_token,
    delete_chat_pending_action,
    get_chat_pending_action,
    store_chat_pending_action,
)
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
from app.services.chatbot_transfer import (
    build_transfer_confirmation_reply,
    extract_transfer_draft,
    is_cancel_message,
    is_confirm_message,
)
from app.services.transfer_service import (
    execute_transfer_by_iban,
    execute_transfer_by_mobile,
)

router = APIRouter()

_TRANSFER_CONFIRMATION_THRESHOLD = 0.8


async def _execute_pending_transfer(
    *,
    pending_action: dict,
    user_id: int,
    current_user: CurrentUser,
    db: AsyncSession,
):
    method = pending_action.get("method")

    if method == "mobile":
        return await execute_transfer_by_mobile(
            sender_id=user_id,
            receiver_phone=str(pending_action["receiver_phone"]),
            amount=Decimal(str(pending_action["amount"])),
            currency=str(pending_action["currency"]),
            x_idempotency_key=str(pending_action["idempotency_key"]),
            current_user=current_user,
            db=db,
        )

    if method == "iban":
        return await execute_transfer_by_iban(
            sender_id=user_id,
            receiver_iban=str(pending_action["receiver_iban"]),
            amount=Decimal(str(pending_action["amount"])),
            currency=str(pending_action["currency"]),
            x_idempotency_key=str(pending_action["idempotency_key"]),
            current_user=current_user,
            db=db,
        )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Unsupported pending action method",
    )


@router.post(
    "/message",
    response_model=ChatbotMessageResponse,
    summary="Send a message to the chatbot",
)
async def send_chatbot_message(
    request: Request,
    body: ChatbotMessageRequest,
    x_action_token: str | None = Header(default=None, alias="X-Action-Token"),
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
    message = body.message.strip()

    start = time.monotonic()
    classification = await classify_intent(message)
    latency_ms = int((time.monotonic() - start) * 1000)

    db.add(
        ChatbotLog(
            user_id=user_id,
            intent=classification.intent,
            confidence=classification.confidence,
            latency_ms=latency_ms,
        )
    )

    try:
        if is_cancel_message(message):
            await delete_chat_pending_action(body.session_id)

            reply = "Okay, I cancelled the pending transfer."
            await save_chat_turn(
                db=db,
                user_id=user_id,
                session_id=body.session_id,
                message=body.message,
                reply=reply,
            )

            return ChatbotMessageResponse(
                reply=reply,
                session_id=body.session_id,
                intent=classification.intent,
                confidence=classification.confidence,
                confirmation_required=False,
            )

        if is_confirm_message(message):
            pending_action = await get_chat_pending_action(body.session_id)

            if pending_action is None:
                reply = (
                    "There is no pending transfer to confirm, or it has expired. "
                    "Please start the transfer again."
                )
                await save_chat_turn(
                    db=db,
                    user_id=user_id,
                    session_id=body.session_id,
                    message=body.message,
                    reply=reply,
                )

                return ChatbotMessageResponse(
                    reply=reply,
                    session_id=body.session_id,
                    intent=classification.intent,
                    confidence=classification.confidence,
                    confirmation_required=False,
                )

            if int(pending_action.get("user_id", -1)) != user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Pending action does not belong to this user",
                )

            if not x_action_token:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Missing X-Action-Token header",
                )

            is_valid = await consume_action_token(current_user.id, x_action_token)

            if not is_valid:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Invalid or expired action token",
                )

            receipt = await _execute_pending_transfer(
                pending_action=pending_action,
                user_id=user_id,
                current_user=current_user,
                db=db,
            )
            await delete_chat_pending_action(body.session_id)

            reply = (
                "Transfer completed: "
                f"{receipt.amount} {receipt.currency} to "
                f"{receipt.receiver_display_name}."
            )
            await save_chat_turn(
                db=db,
                user_id=user_id,
                session_id=body.session_id,
                message=body.message,
                reply=reply,
            )

            return ChatbotMessageResponse(
                reply=reply,
                session_id=body.session_id,
                intent=classification.intent,
                confidence=classification.confidence,
                confirmation_required=False,
                transfer_receipt=receipt,
            )

        confirmation_required = (
            classification.intent == "TRANSFER_INTENT"
            and classification.confidence > _TRANSFER_CONFIRMATION_THRESHOLD
        )

        if confirmation_required:
            draft = extract_transfer_draft(message)

            if draft is None:
                reply = (
                    "I can help with the transfer, but I need the amount, "
                    "currency, and recipient phone number or IBAN first."
                )
                await save_chat_turn(
                    db=db,
                    user_id=user_id,
                    session_id=body.session_id,
                    message=body.message,
                    reply=reply,
                )

                return ChatbotMessageResponse(
                    reply=reply,
                    session_id=body.session_id,
                    intent=classification.intent,
                    confidence=classification.confidence,
                    confirmation_required=False,
                )

            pending_action = draft.to_pending_action(
                user_id=user_id,
                idempotency_key=f"chatbot:{body.session_id}:{uuid4().hex}",
            )
            await store_chat_pending_action(
                body.session_id,
                pending_action,
            )

            reply = build_transfer_confirmation_reply(draft)
            await save_chat_turn(
                db=db,
                user_id=user_id,
                session_id=body.session_id,
                message=body.message,
                reply=reply,
            )

            return ChatbotMessageResponse(
                reply=reply,
                session_id=body.session_id,
                intent=classification.intent,
                confidence=classification.confidence,
                confirmation_required=True,
                pending_action=draft.to_response_payload(),
            )

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
        confirmation_required=False,
    )
