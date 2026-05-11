import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

db_url = os.getenv('DATABASE_URL')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg2://")

engine = create_engine(db_url)

with engine.connect() as conn:
    print("Checking constraints for sync_config...")
    query = """
    SELECT conname, pg_get_constraintdef(c.oid) 
    FROM pg_constraint c 
    JOIN pg_namespace n ON n.oid = c.connamespace 
    WHERE contype = 'c' AND conrelid = 'sync_config'::regclass;
    """
    res = conn.execute(text(query))
    for row in res:
        print(f"Constraint: {row[0]}, Definition: {row[1]}")
