from celery import Celery
from celery.schedules import crontab

from app.core.config import settings


celery_app = Celery(
    "neobank",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.imports = (
    "app.tasks.categorization_tasks",
    "app.tasks.chatbot_tasks",
    "app.tasks.exchange_tasks",
    "app.tasks.kyc_tasks",
    "app.tasks.transaction_tasks",
)

celery_app.conf.beat_schedule = {
    "poll-exchange-rates-every-5-minutes": {
        "task": "app.tasks.exchange_tasks.poll_exchange_rates",
        "schedule": 300.0,
    },
    "retrain-exchange-forecast-weekly": {
        "task": "app.tasks.exchange_tasks.retrain_exchange_forecast",
        "schedule": crontab(hour=3, minute=0, day_of_week="monday"),
    },
    "delete-expired-chat-sessions-daily": {
        "task": "app.tasks.chatbot_tasks.delete_expired_chat_sessions",
        "schedule": crontab(hour=4, minute=0),
    },
}

celery_app.conf.timezone = "Asia/Beirut"
