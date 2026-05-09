from database.db_client import get_db_client

def get_store_settings(client_id: str) -> dict:
    """جلب إعدادات المتجر الأساسية"""
    db = get_db_client()
    try:
        res = db.table("clients").select("company_name, contact_number, email, store_url, logo_url, onboarding_completed").eq("id", client_id).single().execute()
        return res.data if res.data else {}
    except Exception as e:
        print(f"Error fetching store settings: {e}")
        return {}

def update_store_settings(client_id: str, data: dict) -> bool:
    """تحديث إعدادات المتجر الأساسية"""
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
