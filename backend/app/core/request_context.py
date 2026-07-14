"""
DEVATTECH-122 / SP3-703: per-request correlation ID.

A ContextVar so any code running inside a request (endpoint, service,
dependency) can pick up the current request's ID without it being passed
explicitly through every function signature. Set once by the middleware
in main.py at the start of each request; read by the JSON log formatter
and the global exception handler.

Celery tasks do NOT run inside this context (separate process/thread,
no HTTP request) -- they log their own kyc_record_id/transaction_id
instead. See app/tasks/kyc_tasks.py for that pattern.
"""
from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    return request_id_var.get()
