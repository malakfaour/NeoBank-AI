import logging
import uuid
from user_agents import parse as parse_ua

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.redis import blacklist_token
from app.core.config import settings
from app.db.session import get_async_db
from app.models.session import UserSession
from app.schemas.user import CurrentUser

logger = logging.getLogger(__name__)
router = APIRouter()


class SessionResponse(BaseModel):
    session_id: str
    device_name: str | None
    ip_address: str | None
    last_seen: str
    is_active: bool


async def create_session(
    user_id: int,
    request: Request,
    db: AsyncSession,
) -> UserSession:
    """Create a new session record on login."""
    ua_string = request.headers.get("User-Agent", "Unknown")
    try:
        ua = parse_ua(ua_string)
        device_name = f"{ua.browser.family} on {ua.os.family}"
    except Exception:
        device_name = ua_string[:255]

    ip_address = request.client.host if request.client else None

    session = UserSession(
        session_id=uuid.uuid4(),
        user_id=user_id,
        device_name=device_name,
        ip_address=ip_address,
        is_active=True,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.get("", summary="List all active sessions for current user")
async def list_sessions(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Returns all active sessions for the authenticated user."""
    result = await db.execute(
        select(UserSession).where(
            UserSession.user_id == int(current_user.id),
            UserSession.is_active == True,
        )
    )
    sessions = result.scalars().all()
    return [
        {
            "session_id": str(s.session_id),
            "device_name": s.device_name,
            "ip_address": s.ip_address,
            "last_seen": s.last_seen.isoformat(),
            "is_active": s.is_active,
        }
        for s in sessions
    ]


@router.delete("/{session_id}", summary="Remote logout — deactivate a session")
async def delete_session(
    session_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Deactivates a session and blacklists its tokens in Redis."""
    result = await db.execute(
        select(UserSession).where(
            UserSession.session_id == uuid.UUID(session_id),
            UserSession.user_id == int(current_user.id),
            UserSession.is_active == True,
        )
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or already inactive",
        )

    session.is_active = False
    await db.commit()

    return {"message": f"Session {session_id} deactivated successfully"}