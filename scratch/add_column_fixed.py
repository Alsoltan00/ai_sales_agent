import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    print("No DATABASE_URL found.")
    exit(1)

engine = create_engine(DB_URL)

try:
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE column_training ADD COLUMN IF NOT EXISTS on_request BOOLEAN DEFAULT FALSE;"))
        conn.commit()
    print("Successfully added 'on_request' column to 'column_training' table.")
except Exception as e:
    print(f"Error adding column: {e}")
