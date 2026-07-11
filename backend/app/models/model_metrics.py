from sqlalchemy import Column, DateTime, Float, Integer, String
from sqlalchemy.sql import func

from app.db.base import Base


class ModelMetrics(Base):
    __tablename__ = "model_metrics"

    id = Column(Integer, primary_key=True, index=True)
    model_name = Column(String(100), nullable=False, index=True)
    # DEVATTECH-89: relaxed to nullable -- classification models (e.g.
    # XGBoost fraud) have no MAE at all. Existing regression-model writers
    # (exchange forecast retraining, app/tasks/exchange_tasks.py) are
    # unaffected -- they always supply mae; this only changes what is
    # ALLOWED to be omitted, not any existing write path's behavior.
    mae = Column(Float, nullable=True)
    # DEVATTECH-89: AUC for classification models (e.g. XGBoost fraud).
    # Nullable since regression models (e.g. LightGBM exchange forecast)
    # have no AUC.
    auc = Column(Float, nullable=True)
    trained_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
