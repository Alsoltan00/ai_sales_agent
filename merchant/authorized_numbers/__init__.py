import time
from database.db_client import get_db_client

# التخزين المؤقت للإعدادات البسيطة (allow_all, ignore_groups)
_settings_cache = {}
CACHE_TTL = 30 # ثانية

def get_authorized_numbers(client_id: str) -> list:
    """جلب جميع الأرقام المصرّحة لعميل معين"""
    db = get_db_client()
    try:
        res = db.table("authorized_numbers").select("*").eq("client_id", client_id).execute()
        return res.data if res.data else []
    except Exception as e:
        print(f"Error fetching authorized numbers: {e}")
        return []

def add_authorized_number(client_id: str, phone_number: str, label: str = "") -> bool:
    """إضافة رقم مصرح جديد"""
    db = get_db_client()
    try:
        data = {
            "client_id": client_id,
            "phone_number": phone_number,
            "label": label
        }
        db.table("authorized_numbers").insert(data).execute()
        return True
    except Exception as e:
        print(f"Error adding authorized number: {e}")
        return False

def delete_authorized_number(client_id: str, record_id: str) -> bool:
    """حذف رقم مصرح"""
    db = get_db_client()
    try:
        db.table("authorized_numbers").delete().eq("id", record_id).eq("client_id", client_id).execute()
        return True
    except Exception as e:
        print(f"Error deleting authorized number: {e}")
        return False

def _get_client_field(client_id: str, field: str, default=None):
    """جلب حقل واحد من جدول العملاء مع التخزين المؤقت"""
    cache_key = f"{client_id}_{field}"
    now = time.time()
    if cache_key in _settings_cache and now < _settings_cache[cache_key]["expiry"]:
        return _settings_cache[cache_key]["data"]

    db = get_db_client()
    try:
        res = db.table("clients").select(field).eq("id", client_id).single().execute()
        val = res.data.get(field, default) if res.data else default
        _settings_cache[cache_key] = {"data": val, "expiry": now + CACHE_TTL}
        return val
    except:
        return default

def _invalidate_client_cache(client_id: str):
    """مسح التخزين المؤقت لعميل"""
    keys_to_delete = [k for k in _settings_cache if k.startswith(f"{client_id}_")]
    for k in keys_to_delete:
        del _settings_cache[k]

def set_allow_all(client_id: str, allow_all: bool) -> bool:
    """تفعيل أو تعطيل الرد على الجميع"""
    _invalidate_client_cache(client_id)
    db = get_db_client()
    try:
        db.table("clients").update({"allow_all_numbers": allow_all}).eq("id", client_id).execute()
        return True
    except Exception as e:
        print(f"Error setting allow_all: {e}")
        return False

def get_allow_all_status(client_id: str) -> bool:
    return _get_client_field(client_id, "allow_all_numbers", False)

def set_ignore_groups(client_id: str, ignore: bool) -> bool:
    """تفعيل أو تعطيل تجاهل المجموعات"""
    _invalidate_client_cache(client_id)
    db = get_db_client()
    try:
        db.table("clients").update({"ignore_groups": ignore}).eq("id", client_id).execute()
        return True
    except Exception as e:
        print(f"Error setting ignore_groups: {e}")
        return False

def get_ignore_groups_status(client_id: str) -> bool:
    val = _get_client_field(client_id, "ignore_groups", True)
    return val if val is not None else True
