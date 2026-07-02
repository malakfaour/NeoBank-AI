from celery import Celery
from celery.schedules import crontab

from app.core.config import settings


celery_app = Celery(
    "neobank",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.imports = (
    "app.tasks.exchange_tasks",
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
}

celery_app.conf.timezone = "Asia/Beirut"