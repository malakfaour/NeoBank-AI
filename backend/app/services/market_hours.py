from datetime import datetime, time
from zoneinfo import ZoneInfo


MARKET_TIMEZONE = "Asia/Beirut"
MARKET_OPEN_TIME = time(8, 0)
MARKET_CLOSE_TIME = time(17, 0)


def is_market_open() -> bool:
    now = datetime.now(ZoneInfo(MARKET_TIMEZONE))

    # Monday = 0, Sunday = 6
    if now.weekday() >= 5:
        return False

    return MARKET_OPEN_TIME <= now.time() <= MARKET_CLOSE_TIME


def get_market_status() -> dict:
    now = datetime.now(ZoneInfo(MARKET_TIMEZONE))

    return {
        "market_open": is_market_open(),
        "timezone": MARKET_TIMEZONE,
        "current_time": now.isoformat(),
        "opens_at": MARKET_OPEN_TIME.strftime("%H:%M"),
        "closes_at": MARKET_CLOSE_TIME.strftime("%H:%M"),
    }