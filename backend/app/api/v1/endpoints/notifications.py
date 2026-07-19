from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from jwt import ExpiredSignatureError, InvalidTokenError
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.redis import get_redis_client, is_blacklisted
from app.core.security import decode_token
from app.db.session import get_db
from app.models.notification import Notification
from app.models.push_subscription import PushSubscription
from app.schemas.notification import (
    NotificationPageResponse,
    NotificationResponse,
    PushSubscriptionCreate,
    PushSubscriptionResponse,
    ReadAllNotificationsResponse,
)
from app.schemas.auth import CurrentUser

router = APIRouter(prefix="/notifications", tags=["notifications"])


def get_user_id(current_user: CurrentUser) -> int:
    try:
        return int(current_user.id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user id in token",
        ) from exc


async def get_current_user_from_query_token(token: str) -> CurrentUser:
    try:
        payload = decode_token(token)
    except ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        ) from exc
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from exc

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    jti = payload.get("jti")
    user_id = payload.get("sub")

    if not jti or not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token",
        )

    if await is_blacklisted(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )

    role = payload.get("role", "customer")

    return CurrentUser(
        id=user_id,
        token_jti=jti,
        role=role,
    )


@router.get("/stream")
async def stream_notifications(
    request: Request,
    token: str | None = Query(None),
):
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing token",
        )

    current_user = await get_current_user_from_query_token(token)
    user_id = get_user_id(current_user)
    channel = f"notifications:{user_id}"

    async def event_generator():
        redis_client = get_redis_client()
        pubsub = redis_client.pubsub()

        try:
            await pubsub.subscribe(channel)

            while True:
                if await request.is_disconnected():
                    break

                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )

                if message is None:
                    yield ": keep-alive\n\n"
                    continue

                yield f"data: {message['data']}\n\n"

        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/push/subscribe", response_model=PushSubscriptionResponse)
async def subscribe_push_notifications(
    payload: PushSubscriptionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    user_id = get_user_id(current_user)
    token = payload.token.strip()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Push token cannot be blank",
        )

    result = await db.execute(
        select(PushSubscription).where(PushSubscription.token == token)
    )
    subscription = result.scalar_one_or_none()

    if subscription is None:
        subscription = PushSubscription(
            user_id=user_id,
            token=token,
        )
        db.add(subscription)
    else:
        subscription.user_id = user_id

    await db.commit()
    await db.refresh(subscription)

    return subscription


@router.get("", response_model=NotificationPageResponse)
async def list_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    unread_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    user_id = get_user_id(current_user)
    offset = (page - 1) * page_size

    filters = [Notification.user_id == user_id]

    if unread_only:
        filters.append(Notification.read.is_(False))

    total_result = await db.execute(select(func.count(Notification.id)).where(*filters))
    total = total_result.scalar_one()

    notifications_result = await db.execute(
        select(Notification)
        .where(*filters)
        .order_by(Notification.read.asc(), Notification.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    notifications = notifications_result.scalars().all()

    return {
        "items": notifications,
        "page": page,
        "page_size": page_size,
        "total": total or 0,
    }


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
async def mark_notification_as_read(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    user_id = get_user_id(current_user)

    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
        )
    )
    notification = result.scalar_one_or_none()

    if notification is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )

    notification.read = True

    await db.commit()
    await db.refresh(notification)

    return notification


@router.patch("/read-all", response_model=ReadAllNotificationsResponse)
async def mark_all_notifications_as_read(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    user_id = get_user_id(current_user)

    result = await db.execute(
        update(Notification)
        .where(
            Notification.user_id == user_id,
            Notification.read.is_(False),
        )
        .values(read=True)
    )

    await db.commit()

    return {"updated_count": result.rowcount or 0}
