from database.db_client import get_supabase_client

def get_ai_config(client_id: str) -> dict:
    """ط¬ظ„ط¨ ط¥ط¹ط¯ط§ط¯ط§طھ ط§ظ„ط°ظƒط§ط، ط§ظ„ط§طµط·ظ†ط§ط¹ظٹ (ط§ظ„ظ†ظ…ظˆط°ط¬ ظˆظ…ظپطھط§ط­ API)"""
    supabase = get_supabase_client()
    try:
        res = supabase.table("ai_models_config").select("*").eq("client_id", client_id).single().execute()
        return res.data if res.data else {}
    except Exception as e:
        print(f"Error fetching AI config: {e}")
        return {}

def update_ai_config(client_id: str, data: dict) -> bool:
    """طھط­ط¯ظٹط« ط¥ط¹ط¯ط§ط¯ط§طھ ط§ظ„ط°ظƒط§ط، ط§ظ„ط§طµط·ظ†ط§ط¹ظٹ"""
    supabase = get_supabase_client()
    try:
        # Check if config exists
        existing = get_ai_config(client_id)
        
        allowed_fields = ["model_name", "provider", "api_key", "model_id"]
        update_data = {k: v for k, v in data.items() if k in allowed_fields}
        update_data["client_id"] = client_id
        
        if existing:
            supabase.table("ai_models_config").update(update_data).eq("client_id", client_id).execute()
        else:
            supabase.table("ai_models_config").insert(update_data).execute()
            
        return True
    except Exception as e:
        print(f"Error updating AI config: {e}")
        return False
