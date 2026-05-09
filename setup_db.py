import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL")
if DB_URL and DB_URL.startswith("postgres://"):
    DB_URL = DB_URL.replace("postgres://", "postgresql+psycopg2://")

print(f"Connecting to: {DB_URL}")

try:
    print(f"Initializing database connection...")
    engine = create_engine(DB_URL)
    
    print(f"Reading schema.sql...")
    with open("database/schema.sql", "r", encoding="utf-8-sig") as f:
        sql_commands = f.read()

    print(f"Executing SQL commands...")
    with engine.begin() as conn:
        # Split by semicolon but ignore semicolons inside quotes if possible
        # For simplicity, we just execute the whole block if the driver supports it
        # Or execute one by one
        statements = sql_commands.split(';')
        for i, stmt in enumerate(statements):
            stmt = stmt.strip()
            if stmt:
                try:
                    conn.execute(text(stmt))
                except Exception as stmt_e:
                    print(f"Warning: Error in statement {i}: {stmt_e}")
                    # Continue to next statement
    
    print("[SUCCESS] Database setup process completed!")
except Exception as e:
    print(f"[ERROR] Database setup failed: {e}")
    import traceback
    traceback.print_exc()
