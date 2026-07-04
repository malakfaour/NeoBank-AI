from datetime import datetime

from pydantic import BaseModel


class AuditLogEntry(BaseModel):
    id: int
    action: str
    actor_id: int | None
    timestamp: datetime
    metadata: dict | None


class AuditTrailResponse(BaseModel):
    transaction_id: int
    entries: list[AuditLogEntry]
