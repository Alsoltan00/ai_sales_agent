import time
import asyncio
from database.db_client import get_db_client

_cache = {}
CACHE_TTL = 30 # ثانية

def _fetch_planning_sync(client_id: str):
    """جلب متزامن من قاعدة البيانات - يعمل في thread منفصل"""
    db = get_db_client()
    res = db.table("planning_config").select("sales_agent_name, dialect_instructions, company_description, store_activity, sales_type, order_flow, delivery_type, custom_instructions, ai_temperature, ai_max_tokens, ai_core_strategy").eq("client_id", client_id).single().execute()
    if res.data:
        return {
            "ai_agent_name": res.data.get("sales_agent_name"),
            "ai_tone": res.data.get("dialect_instructions"),
            "business_description": res.data.get("company_description"),
            "store_activity": res.data.get("store_activity"),
            "sales_type": res.data.get("sales_type"),
            "order_flow": res.data.get("order_flow"),
            "delivery_type": res.data.get("delivery_type"),
            "custom_instructions": res.data.get("custom_instructions", ""),
            "ai_temperature": float(res.data.get("ai_temperature") or 0.1),
            "ai_max_tokens": int(res.data.get("ai_max_tokens") or 600),
            "ai_core_strategy": res.data.get("ai_core_strategy", "")
        }
    return {}

async def get_planning_config(client_id: str):
    """جلب إعدادات التخطيط مع التخزين المؤقت + عدم حجب الـ Event Loop"""
    global _cache
    now = time.time()
    if client_id in _cache and now - _cache[client_id]['timestamp'] < CACHE_TTL:
        return _cache[client_id]['data']
        
    try:
        from database.db_client import DB_EXECUTOR
        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(DB_EXECUTOR, _fetch_planning_sync, client_id)
        _cache[client_id] = {'timestamp': now, 'data': data}
        return data
    except Exception as e:
        print(f"[PLANNING ERROR] Failed to fetch config for {client_id}: {e}")
        return {}

def update_planning_config(client_id: str, data: dict) -> bool:
    """تحديث إعدادات التخطيط"""
    global _cache
    if client_id in _cache:
        del _cache[client_id]
        
    db = get_db_client()
    try:
        # خريطة تحويل من أسماء الحقول في الفرونت إند إلى أسماء الأعمدة في قاعدة البيانات
        field_map = {
            "ai_agent_name": "sales_agent_name",
            "ai_tone": "dialect_instructions",
            "business_description": "company_description",
            "store_activity": "store_activity",
            "sales_type": "sales_type",
            "order_flow": "order_flow",
            "delivery_type": "delivery_type",
            "custom_instructions": "custom_instructions",
            "ai_temperature": "ai_temperature",
            "ai_max_tokens": "ai_max_tokens",
            "ai_core_strategy": "ai_core_strategy"
        }
        
        update_data = {}
        for k, v in data.items():
            if k in field_map:
                update_data[field_map[k]] = v
        
        if update_data:
            update_data["client_id"] = client_id
            # استخدام upsert لضمان إنشاء السجل إذا لم يكن موجوداً
            db.table("planning_config").upsert(update_data).execute()
        return True
    except Exception as e:
        print(f"Error updating planning config: {e}")
        return False
