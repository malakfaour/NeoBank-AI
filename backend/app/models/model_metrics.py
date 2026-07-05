from sqlalchemy import Column, Integer, String, Float, DateTime
from sqlalchemy.sql import func

from app.db.base import Base


class ModelMetrics(Base):
    __tablename__ = "model_metrics"

    id = Column(Integer, primary_key=True, index=True)
    model_name = Column(String, index=True, nullable=False)
    mae = Column(Float, nullable=False)

    trained_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)