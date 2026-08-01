from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from app.celery_app import celery_app
from app.core.config import settings
from app.db.sync_session import SyncSessionLocal
from app.models.chat_session import ChatSession


@celery_app.task(
    name="app.tasks.chatbot_tasks.delete_expired_chat_sessions"
)
def delete_expired_chat_sessions() -> int:
    """Delete conversations whose last activity is outside the retention window."""
    cutoff = datetime.now(timezone.utc) - timedelta(
        days=settings.CHATBOT_SESSION_RETENTION_DAYS
    )

    with SyncSessionLocal() as db:
        result = db.execute(
            delete(ChatSession).where(ChatSession.updated_at < cutoff)
        )
        db.commit()
        return result.rowcount
