import time
from decimal import Decimal
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.redis import (
    consume_action_token,
    delete_chat_incomplete_action,
    delete_chat_pending_action,
    get_chat_incomplete_action,
    get_chat_pending_action,
    store_chat_incomplete_action,
    store_chat_pending_action,
)
from app.db.session import get_async_db
from app.models.chatbot_log import ChatbotLog
from app.schemas.chatbot import (
    ChatbotMessageRequest,
    ChatbotHistoryResponse,
    ChatbotMessageResponse,
)
from app.schemas.auth import CurrentUser
from app.services.chatbot_intent import classify_intent
from app.services.rate_limiter import check_rate_limit
from app.services.chatbot_service import (
    ChatSessionOwnershipError,
    get_chat_history,
    get_chatbot_response,
    save_chat_turn,
)
from app.services.chatbot_transfer import (
    ChatbotPartialTransferDraft,
    build_incomplete_transfer_reply,
    build_transfer_confirmation_reply,
    extract_partial_transfer_draft,
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
            await delete_chat_incomplete_action(body.session_id)
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

        stored_partial = await get_chat_incomplete_action(body.session_id)
        partial = None
        if stored_partial is not None:
            if int(stored_partial.get("user_id", -1)) == user_id:
                partial = ChatbotPartialTransferDraft.from_storage_payload(stored_partial)
            else:
                await delete_chat_incomplete_action(body.session_id)

        contribution = extract_partial_transfer_draft(message)
        if partial is not None and not contribution.supplies_any(
            partial.missing_fields()
        ):
            await delete_chat_incomplete_action(body.session_id)
            partial = None

        if confirmation_required or partial is not None:
            accumulated = (
                partial.merge(contribution) if partial is not None else contribution
            )
            draft = accumulated.to_complete_draft()

            if draft is None:
                if accumulated.has_fields():
                    await store_chat_incomplete_action(
                        body.session_id,
                        accumulated.to_storage_payload(user_id=user_id),
                    )
                reply = build_incomplete_transfer_reply(accumulated)
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

            await delete_chat_incomplete_action(body.session_id)
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


@router.get(
    "/history",
    response_model=ChatbotHistoryResponse,
    summary="Get stored chatbot conversation history",
)
async def get_chatbot_history(
    session_id: str = Query(..., min_length=1, max_length=64),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> ChatbotHistoryResponse:
    user_id = int(current_user.id)

    try:
        messages = await get_chat_history(
            db=db,
            user_id=user_id,
            session_id=session_id,
        )
    except ChatSessionOwnershipError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    if messages is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found",
        )

    return ChatbotHistoryResponse(
        session_id=session_id,
        messages=messages,
    )
