from database.db_client import get_supabase_client

def get_channels_config(client_id: str) -> dict:
    """ط¬ظ„ط¨ ط¥ط¹ط¯ط§ط¯ط§طھ ط§ظ„ظ‚ظ†ظˆط§طھ (ظˆط§طھط³ط§ط¨ / طھظٹظ„ظٹط¬ط±ط§ظ…)"""
    supabase = get_supabase_client()
    try:
        res = supabase.table("channels_config").select("*").eq("client_id", client_id).single().execute()
        return res.data if res.data else {}
    except Exception as e:
        print(f"Error fetching channels config: {e}")
        return {}

def update_channels_config(client_id: str, data: dict) -> bool:
    """طھط­ط¯ظٹط« ط¥ط¹ط¯ط§ط¯ط§طھ ط§ظ„ظ‚ظ†ظˆط§طھ"""
    supabase = get_supabase_client()
    try:
        existing = get_channels_config(client_id)
        
        allowed_fields = [
            "telegram_bot_token", "whatsapp_provider", 
            "evolution_api_url", "evolution_api_key", "evolution_instance_name",
            "meta_phone_number_id", "meta_access_token", "meta_verify_token"
        ]
        update_data = {k: v for k, v in data.items() if k in allowed_fields}
        update_data["client_id"] = client_id
        
        if existing:
            supabase.table("channels_config").update(update_data).eq("client_id", client_id).execute()
        else:
            supabase.table("channels_config").insert(update_data).execute()
            
        return True
    except Exception as e:
        print(f"Error updating channels config: {e}")
        return False
