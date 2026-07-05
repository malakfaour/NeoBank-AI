from sqlalchemy import create_engine, text
from app.core.config import settings

url = settings.DATABASE_URL_DIRECT
engine = create_engine(url)

with engine.connect() as conn:
    result = conn.execute(text("SELECT id, email FROM users"))
    for row in result:
        print(row)