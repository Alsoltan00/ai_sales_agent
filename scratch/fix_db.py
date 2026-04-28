import os
from sqlalchemy import create_engine, text
import json

DB_URL = os.getenv("DATABASE_URL", "")
if DB_URL:
    if DB_URL.startswith("mysql://"):
        DB_URL = DB_URL.replace("mysql://", "mysql+pymysql://", 1)
    elif DB_URL.startswith("postgres://"):
        DB_URL = DB_URL.replace("postgres://", "postgresql+psycopg2://", 1)
    elif DB_URL.startswith("postgresql://") and not DB_URL.startswith("postgresql+psycopg2://"):
        DB_URL = DB_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

engine = create_engine(DB_URL)

try:
    with engine.connect() as conn:
        # Check clients table
        print("Checking 'clients' table columns...")
        res = conn.execute(text("SELECT * FROM clients LIMIT 1"))
        print(f"Columns: {res.keys()}")
        
        # Check if we can add them if missing
        print("Attempting to add columns if missing...")
        conn.execute(text("ALTER TABLE clients ADD COLUMN IF NOT EXISTS subscription_plan TEXT DEFAULT 'free';"))
        conn.execute(text("ALTER TABLE clients ADD COLUMN IF NOT EXISTS subscription_ends_at TIMESTAMP;"))
        conn.commit()
        print("Done.")
except Exception as e:
    print(f"Error: {e}")
