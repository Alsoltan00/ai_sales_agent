import time
import asyncio
from database.db_client import get_db_client

_cache = {}
CACHE_TTL = 30 # ثانية

def _fetch_settings_sync(client_id: str):
    """جلب متزامن من قاعدة البيانات - يعمل في thread منفصل"""
    db = get_db_client()
    res = db.table("clients").select("company_name, contact_number, email, store_url, logo_url, onboarding_completed").eq("id", client_id).single().execute()
    return res.data if res.data else {}

async def get_store_settings(client_id: str):
    """جلب إعدادات المتجر مع التخزين المؤقت - بدون asyncio.to_thread لتجنب اختناق thread pool"""
    now = time.time()
    if client_id in _cache:
        if now < _cache[client_id]["expiry"]:
            return _cache[client_id]["data"]

    try:
        data = _fetch_settings_sync(client_id)
        _cache[client_id] = {"data": data, "expiry": now + CACHE_TTL}
        return data
    except Exception as e:
        print(f"[CACHE ERROR] Failed to fetch store settings for {client_id}: {e}")
        return {}

def update_store_settings(client_id: str, data: dict) -> bool:
    """تحديث إعدادات المتجر الأساسية"""
    global _cache
    if client_id in _cache:
        del _cache[client_id]
        
    db = get_db_client()
    try:
        allowed_fields = ["company_name", "contact_number", "email", "store_url", "logo_url", "onboarding_completed"]
        update_data = {k: v for k, v in data.items() if k in allowed_fields}
        
        if update_data:
            db.table("clients").update(update_data).eq("id", client_id).execute()
        return True
    except Exception as e:
        print(f"Error updating store settings: {e}")
        return False
