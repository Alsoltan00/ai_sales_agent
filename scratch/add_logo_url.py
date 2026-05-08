import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL")
if DB_URL and DB_URL.startswith("postgres://"):
    DB_URL = DB_URL.replace("postgres://", "postgresql+psycopg2://")

try:
    engine = create_engine(DB_URL)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE clients ADD COLUMN IF NOT EXISTS logo_url TEXT;"))
    print("Column added successfully.")
except Exception as e:
    print(f"Error: {e}")
