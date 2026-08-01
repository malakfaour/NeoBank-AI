from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.chat_session import ChatSession
from app.tasks import chatbot_tasks


def test_delete_expired_chat_sessions_is_idempotent(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    ChatSession.__table__.create(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)

    with Session(engine) as db:
        db.add_all(
            [
                ChatSession(
                    session_id="expired-chat-session",
                    user_id=1,
                    messages=[{"role": "user", "content": "old"}],
                    created_at=now - timedelta(days=40),
                    updated_at=now - timedelta(days=31),
                ),
                ChatSession(
                    session_id="current-chat-session",
                    user_id=1,
                    messages=[{"role": "user", "content": "current"}],
                    created_at=now - timedelta(days=20),
                    updated_at=now - timedelta(days=29),
                ),
            ]
        )
        db.commit()

    monkeypatch.setattr(chatbot_tasks, "SyncSessionLocal", session_factory)
    monkeypatch.setattr(
        chatbot_tasks.settings,
        "CHATBOT_SESSION_RETENTION_DAYS",
        30,
    )

    assert chatbot_tasks.delete_expired_chat_sessions.run() == 1
    assert chatbot_tasks.delete_expired_chat_sessions.run() == 0

    with Session(engine) as db:
        remaining_ids = set(
            db.scalars(select(ChatSession.session_id)).all()
        )

    assert remaining_ids == {"current-chat-session"}
