import time
from database.db_client import get_db_client

_cache = {}
CACHE_TTL = 30 # ثانية

def get_channels_config(client_id: str) -> dict:
    """جلب إعدادات القنوات مع التخزين المؤقت"""
    now = time.time()
    if client_id in _cache and now < _cache[client_id]["expiry"]:
        return _cache[client_id]["data"]

    db = get_db_client()
    try:
        res = db.table("channels_config").select("*").eq("client_id", client_id).single().execute()
        data = res.data if res.data else {}
        _cache[client_id] = {"data": data, "expiry": now + CACHE_TTL}
        return data
    except Exception as e:
        print(f"Error fetching channels config: {e}")
        return {}

def update_channels_config(client_id: str, data: dict) -> bool:
    """تحديث إعدادات القنوات باستخدام upsert (بدون استعلام فحص مسبق)"""
    global _cache
    if client_id in _cache:
        del _cache[client_id]

    db = get_db_client()
    try:
        allowed_fields = [
            "telegram_bot_token", "whatsapp_provider", 
            "evolution_api_url", "evolution_api_key", "evolution_instance_name",
            "meta_phone_number_id", "meta_access_token", "meta_verify_token",
            "instagram_access_token", "instagram_page_id",
            "tiktok_access_token", "tiktok_shop_id"
        ]
        update_data = {k: v for k, v in data.items() if k in allowed_fields}
        update_data["client_id"] = client_id
        
        # استخدام upsert بدلاً من check-then-insert (استعلام واحد بدل اثنين)
        db.table("channels_config").upsert(update_data).execute()
        return True
    except Exception as e:
        print(f"Error updating channels config: {e}")
        return False
