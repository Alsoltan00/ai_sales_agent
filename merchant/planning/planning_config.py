from database.db_client import get_supabase_client

def get_planning_config(client_id: str) -> dict:
    """جلب إعدادات التخطيط والذكاء الاصطناعي"""
    supabase = get_supabase_client()
    try:
        res = supabase.table("planning_config").select("sales_agent_name, dialect_instructions, company_description, store_activity").eq("client_id", client_id).single().execute()
        if res.data:
            return {
                "ai_agent_name": res.data.get("sales_agent_name"),
                "ai_tone": res.data.get("dialect_instructions"),
                "business_description": res.data.get("company_description"),
                "store_activity": res.data.get("store_activity")
            }
        return {}
    except Exception as e:
        print(f"Error fetching planning config: {e}")
        return {}

def update_planning_config(client_id: str, data: dict) -> bool:
    """تحديث إعدادات التخطيط"""
    supabase = get_supabase_client()
    try:
        # خريطة تحويل من أسماء الحقول في الفرونت إند إلى أسماء الأعمدة في قاعدة البيانات
        field_map = {
            "ai_agent_name": "sales_agent_name",
            "ai_tone": "dialect_instructions",
            "business_description": "company_description",
            "store_activity": "store_activity"
        }
        
        update_data = {}
        for k, v in data.items():
            if k in field_map:
                update_data[field_map[k]] = v
        
        if update_data:
            update_data["client_id"] = client_id
            # استخدام upsert لضمان إنشاء السجل إذا لم يكن موجوداً
            supabase.table("planning_config").upsert(update_data).execute()
        return True
    except Exception as e:
        print(f"Error updating planning config: {e}")
        return False
