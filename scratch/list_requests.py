from sqlalchemy import create_engine, text
import os

DB_URL = os.getenv("DATABASE_URL", "")
if DB_URL.startswith("postgres://"):
    DB_URL = DB_URL.replace("postgres://", "postgresql+psycopg2://", 1)

engine = create_engine(DB_URL)

with engine.connect() as conn:
    result = conn.execute(text("SELECT id, company_name, contact_number, status, created_at FROM new_client_requests ORDER BY created_at DESC LIMIT 5"))
    for row in result:
        print(row)
