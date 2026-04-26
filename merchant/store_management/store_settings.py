from database.db_client import get_supabase_client

def get_store_settings(client_id: str) -> dict:
    """ط¬ظ„ط¨ ط¥ط¹ط¯ط§ط¯ط§طھ ط§ظ„ظ…طھط¬ط± ط§ظ„ط£ط³ط§ط³ظٹط©"""
    supabase = get_supabase_client()
    try:
        res = supabase.table("clients").select("company_name, contact_number, email, store_url").eq("id", client_id).single().execute()
        return res.data if res.data else {}
    except Exception as e:
        print(f"Error fetching store settings: {e}")
        return {}

def update_store_settings(client_id: str, data: dict) -> bool:
    """طھط­ط¯ظٹط« ط¥ط¹ط¯ط§ط¯ط§طھ ط§ظ„ظ…طھط¬ط± ط§ظ„ط£ط³ط§ط³ظٹط©"""
    supabase = get_supabase_client()
    try:
        # ط§ظ„ط³ظ…ط§ط­ ط¨طھط­ط¯ظٹط« ظ‡ط°ظ‡ ط§ظ„ط­ظ‚ظˆظ„ ظپظ‚ط·
        allowed_fields = ["company_name", "contact_number", "email", "store_url"]
        update_data = {k: v for k, v in data.items() if k in allowed_fields}
        
        if update_data:
            supabase.table("clients").update(update_data).eq("id", client_id).execute()
        return True
    except Exception as e:
        print(f"Error updating store settings: {e}")
        return False
