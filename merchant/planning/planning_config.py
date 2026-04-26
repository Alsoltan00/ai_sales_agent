from database.db_client import get_supabase_client

def get_planning_config(client_id: str) -> dict:
    """ط¬ظ„ط¨ ط¥ط¹ط¯ط§ط¯ط§طھ ط§ظ„طھط®ط·ظٹط· ظˆط§ظ„ط°ظƒط§ط، ط§ظ„ط§طµط·ظ†ط§ط¹ظٹ"""
    supabase = get_supabase_client()
    try:
        res = supabase.table("clients").select("ai_agent_name, ai_tone, business_description").eq("id", client_id).single().execute()
        return res.data if res.data else {}
    except Exception as e:
        print(f"Error fetching planning config: {e}")
        return {}

def update_planning_config(client_id: str, data: dict) -> bool:
    """طھط­ط¯ظٹط« ط¥ط¹ط¯ط§ط¯ط§طھ ط§ظ„طھط®ط·ظٹط·"""
    supabase = get_supabase_client()
    try:
        allowed_fields = ["ai_agent_name", "ai_tone", "business_description"]
        update_data = {k: v for k, v in data.items() if k in allowed_fields}
        
        if update_data:
            supabase.table("clients").update(update_data).eq("id", client_id).execute()
        return True
    except Exception as e:
        print(f"Error updating planning config: {e}")
        return False
