import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

db_url = os.getenv('DATABASE_URL')
if not db_url:
    print("DATABASE_URL not found")
    exit(1)
    
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg2://")

engine = create_engine(db_url)

with engine.connect() as conn:
    print("Trying to drop the constraint directly...")
    try:
        # We usually name it sync_config_source_type_check based on schema.sql or automatic naming
        conn.execute(text("ALTER TABLE sync_config DROP CONSTRAINT IF EXISTS sync_config_source_type_check"))
        conn.commit()
        print("Constraint dropped (if existed).")
    except Exception as e:
        print("Error dropping constraint:", e)
    
    print("Trying to add the updated constraint...")
    try:
        conn.execute(text("ALTER TABLE sync_config ADD CONSTRAINT sync_config_source_type_check CHECK (source_type IN ('supabase', 'aiven', 'google_sheets', 'excel'))"))
        conn.commit()
        print("Constraint added successfully.")
    except Exception as e:
        print("Error adding constraint:", e)
