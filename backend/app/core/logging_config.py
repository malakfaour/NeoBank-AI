"""
DEVATTECH-122 / SP3-703: structured logging setup.

Two output modes, switched by settings.LOG_FORMAT:
  "text" (default, dev-friendly) -- plain "LEVEL logger: message"
  "json" (prod)                  -- one JSON object per line

In both modes, every log record automatically carries the current
request's ID (from app.core.request_context) if one is set -- no need
to pass it manually at each call site. Celery tasks run outside any
request context, so their records get request_id=null; they should
instead pass their own correlation id explicitly, e.g.:
    logger.info("KYC processed", extra={"kyc_record_id": kyc_record_id})
Those extra fields are automatically included in JSON output too.
"""
import json
import logging
import sys
from datetime import datetime, timezone

from app.core.request_context import get_request_id

# Attributes every stdlib LogRecord has -- anything else set via extra={}
# is something a call site deliberately added, and gets surfaced in the
# JSON output as its own field.
_STANDARD_LOG_RECORD_ATTRS = set(logging.LogRecord(
    "", 0, "", 0, "", (), None
).__dict__.keys()) | {"message", "asctime", "request_id"}


class _RequestIdFilter(logging.Filter):
    """Attaches the current request_id (or None) to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
        }

        for key, value in record.__dict__.items():
            if key not in _STANDARD_LOG_RECORD_ATTRS:
                payload[key] = value

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


class _TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        request_id = getattr(record, "request_id", None)
        prefix = f"[{request_id}] " if request_id else ""
        base = f"{record.levelname} {record.name}: {prefix}{record.getMessage()}"
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def configure_logging(log_format: str) -> None:
    """
    Call once at app/worker startup. log_format is settings.LOG_FORMAT
    ("text" or "json").
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_RequestIdFilter())
    handler.setFormatter(_JsonFormatter() if log_format == "json" else _TextFormatter())

    app_logger = logging.getLogger("app")
    app_logger.handlers.clear()
    app_logger.addHandler(handler)
    app_logger.setLevel(logging.INFO)
    app_logger.propagate = False
