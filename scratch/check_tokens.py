from database.db_client import get_db_client
import json

def check_tokens():
    try:
        db = get_db_client()
        res = db.table('channels_config').select('meta_verify_token').execute()
        print(json.dumps(res.data, indent=2))
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_tokens()
