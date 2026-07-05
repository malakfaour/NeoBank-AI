from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.notification import Notification
from app.schemas.notification import (
    NotificationPageResponse,
    NotificationResponse,
    ReadAllNotificationsResponse,
)
from app.schemas.user import CurrentUser

router = APIRouter(prefix="/notifications", tags=["notifications"])


def get_user_id(current_user: CurrentUser) -> int:
    try:
        return int(current_user.id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user id in token",
        ) from exc


@router.get("", response_model=NotificationPageResponse)
async def list_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    user_id = get_user_id(current_user)
    offset = (page - 1) * page_size

    total_result = await db.execute(
        select(func.count(Notification.id)).where(Notification.user_id == user_id)
    )
    total = total_result.scalar_one()

    notifications_result = await db.execute(
        select(Notification)
        .where(Notification.user_id == user_id)
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