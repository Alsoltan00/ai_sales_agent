import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL")
if DB_URL and DB_URL.startswith("postgres://"):
    DB_URL = DB_URL.replace("postgres://", "postgresql+psycopg2://")

print(f"Connecting to: {DB_URL}")

try:
    engine = create_engine(DB_URL)
    with open("database/schema.sql", "r", encoding="utf-8-sig") as f:
        sql_commands = f.read()

    with engine.begin() as conn:
        for stmt in sql_commands.split(';'):
            stmt = stmt.strip()
            if stmt:
                conn.execute(text(stmt))
    print("[SUCCESS] Tables created successfully in Aiven!")
except Exception as e:
    print(f"[ERROR] Database creation failed: {e}")
