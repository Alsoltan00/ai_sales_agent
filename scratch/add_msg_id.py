from database.db_client import get_db_engine
from sqlalchemy import text

def add_message_id_column():
    engine = get_db_engine()
    if not engine:
        print("No engine")
        return
    
    with engine.begin() as conn:
        try:
            # Check if column exists
            is_postgres = "postgres" in str(engine.url) or "postgresql" in str(engine.url)
            
            if is_postgres:
                conn.execute(text("ALTER TABLE message_logs ADD COLUMN IF NOT EXISTS message_id TEXT;"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_message_logs_msg_id ON message_logs(message_id);"))
            else:
                # MySQL doesn't support ADD COLUMN IF NOT EXISTS easily in standard SQL
                # We'll just try and catch
                try:
                    conn.execute(text("ALTER TABLE message_logs ADD COLUMN message_id VARCHAR(255);"))
                    conn.execute(text("CREATE INDEX idx_message_logs_msg_id ON message_logs(message_id);"))
                except Exception as e:
                    print(f"MySQL error (likely column exists): {e}")
            
            print("Successfully added message_id column to message_logs")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    add_message_id_column()
