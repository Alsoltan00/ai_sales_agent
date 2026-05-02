import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

DB_URL = os.getenv("DATABASE_URL", "")
if DB_URL.startswith("mysql://"):
    DB_URL = DB_URL.replace("mysql://", "mysql+pymysql://", 1)
elif DB_URL.startswith("postgres://"):
    DB_URL = DB_URL.replace("postgres://", "postgresql+psycopg2://", 1)
elif DB_URL.startswith("postgresql://") and not DB_URL.startswith("postgresql+psycopg2://"):
    DB_URL = DB_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

engine = create_engine(DB_URL)

def migrate():
    with engine.begin() as conn:
        print("Running migration...")
        try:
            # Check for Postgres
            if "postgres" in DB_URL or "postgresql" in DB_URL:
                conn.execute(text("ALTER TABLE message_logs ADD COLUMN IF NOT EXISTS message_id TEXT;"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_message_logs_msg_id ON message_logs(message_id);"))
                print("Postgres migration success")
            else:
                # MySQL
                try:
                    conn.execute(text("ALTER TABLE message_logs ADD COLUMN message_id VARCHAR(255);"))
                    conn.execute(text("CREATE INDEX idx_message_logs_msg_id ON message_logs(message_id);"))
                    print("MySQL migration success")
                except Exception as e:
                    print(f"MySQL warning (column may exist): {e}")
        except Exception as e:
            print(f"Migration error: {e}")

if __name__ == "__main__":
    migrate()
