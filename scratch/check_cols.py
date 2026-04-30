from database.db_client import get_db_client
import json

def check():
    db = get_db_client()
    try:
        # Try to get one row to see column names
        res = db.table("message_logs").select("*").limit(1).execute()
        if res.data:
            print("Columns found:", list(res.data[0].keys()))
        else:
            print("No data in message_logs to infer columns.")
    except Exception as e:
        print("Error checking columns:", e)

if __name__ == "__main__":
    check()
