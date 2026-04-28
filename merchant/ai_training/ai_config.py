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
    """تنشيط نموذج معين بناء على الـ ID الخاص بالصف في الداتابيز وإلغاء تنشيط البقية"""
    supabase = get_supabase_client()
    try:
        # تحويل الـ ID إلى رقم في حال كان النظام يستخدم Serial ID
        try:
            target_id = int(model_id_pk)
        except:
            target_id = model_id_pk

        # 1. إلغاء تفعيل الجميع لهذا العميل
        supabase.table("ai_models_config").update({"is_active": False}).eq("client_id", client_id).execute()
        
        # 2. تفعيل النموذج المطلوب فقط
        supabase.table("ai_models_config").update({"is_active": True}).eq("id", target_id).eq("client_id", client_id).execute()
        
        return True
    except Exception as e:
        print(f"Error activating model: {e}")
        return False
