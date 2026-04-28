from database.db_client import get_supabase_client

def get_ai_config(client_id: str) -> dict:
    """جلب إعدادات الذكاء الاصطناعي النشطة حاليا"""
    supabase = get_supabase_client()
    try:
        res = supabase.table("ai_models_config").select("*").eq("client_id", client_id).eq("is_active", True).execute()
        return res.data[0] if res.data else {}
    except Exception as e:
        print(f"Error fetching active AI config: {e}")
        return {}

def get_all_ai_configs(client_id: str) -> list:
    """جلب جميع النماذج المحفوظة للتاجر"""
    supabase = get_supabase_client()
    try:
        res = supabase.table("ai_models_config").select("*").eq("client_id", client_id).execute()
        return res.data if res.data else []
    except Exception as e:
        print(f"Error fetching all AI configs: {e}")
        return []

def update_ai_config(client_id: str, data: dict) -> bool:
    """إضافة نموذج جديد وجعله النشط، وإلغاء تنشيط البقية"""
    supabase = get_supabase_client()
    try:
        allowed_fields = ["model_name", "provider", "api_key", "model_id"]
        insert_data = {k: v for k, v in data.items() if k in allowed_fields}
        insert_data["client_id"] = client_id
        insert_data["is_active"] = True # Make the new one active by default
        
        # Deactivate all existing models for this client
        supabase.table("ai_models_config").update({"is_active": False}).eq("client_id", client_id).execute()
        
        # Insert the new model
        supabase.table("ai_models_config").insert(insert_data).execute()
            
        return True
    except Exception as e:
        print(f"Error adding AI config: {e}")
        return False

def activate_ai_model(client_id: str, model_id_pk: str) -> bool:
    """تنشيط نموذج معين باستخدام SQL مباشر لضمان الدقة"""
    from database.db_client import get_db_engine
    from sqlalchemy import text
    engine = get_db_engine()
    if not engine:
        return False
        
    try:
        clean_id = str(model_id_pk).strip()
        with engine.begin() as conn:
            # 1. إلغاء تفعيل الجميع لهذا العميل
            conn.execute(
                text("UPDATE ai_models_config SET is_active = False WHERE client_id = :cid"),
                {"cid": client_id}
            )
            # 2. تفعيل النموذج المختار
            conn.execute(
                text("UPDATE ai_models_config SET is_active = True WHERE id = :mid AND client_id = :cid"),
                {"mid": clean_id, "cid": client_id}
            )
        return True
    except Exception as e:
        print(f"[ERROR] SQL Activation failed: {e}")
        return False
