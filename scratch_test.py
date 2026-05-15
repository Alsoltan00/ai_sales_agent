from database.db_client import get_db_client
import traceback
try:
    db = get_db_client()
    res = db.table('merchant_manual_data').select('id, data->0').limit(1).execute()
    print("SUCCESS", res.data)
except Exception as e:
    traceback.print_exc()
