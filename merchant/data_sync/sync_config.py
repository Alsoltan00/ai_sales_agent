import time
from database.db_client import get_db_client

_cache = {}
CACHE_TTL = 30 # ثانية

def get_sync_config(client_id: str) -> dict:
    """جلب إعدادات مزامنة البيانات مع التخزين المؤقت"""
    now = time.time()
    if client_id in _cache and now < _cache[client_id]["expiry"]:
        return _cache[client_id]["data"]

    db = get_db_client()
    try:
        res = db.table("sync_config").select("*").eq("client_id", client_id).single().execute()
        data = res.data if res.data else {}
        _cache[client_id] = {"data": data, "expiry": now + CACHE_TTL}
        return data
    except Exception as e:
        print(f"Error fetching sync config: {e}")
        return {}

def update_sync_config(client_id: str, data: dict) -> bool:
    """تحديث إعدادات المزامنة باستخدام upsert"""
    global _cache
    if client_id in _cache:
        del _cache[client_id]

    db = get_db_client()
    try:
        connection_details = data.get("connection_details", {})
        update_data = {
            "client_id": client_id,
            "source_type": data.get("source_type"),
            "connection_details": connection_details,
            "table_name": data.get("table_name", ""),
            "sheet_name": data.get("sheet_name", ""),
        }
        
        # استخدام upsert بدلاً من check-then-insert
        db.table("sync_config").upsert(update_data).execute()
        return True
    except Exception as e:
        print(f"Error updating sync config: {e}")
        return False
