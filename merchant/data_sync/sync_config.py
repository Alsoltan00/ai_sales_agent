from database.db_client import get_supabase_client
import json

def get_sync_config(client_id: str) -> dict:
    """ط¬ظ„ط¨ ط¥ط¹ط¯ط§ط¯ط§طھ ظ…ط²ط§ظ…ظ†ط© ط§ظ„ط¨ظٹط§ظ†ط§طھ (Supabase, Aiven, Sheets)"""
    supabase = get_supabase_client()
    try:
        res = supabase.table("sync_config").select("*").eq("client_id", client_id).single().execute()
        return res.data if res.data else {}
    except Exception as e:
        print(f"Error fetching sync config: {e}")
        return {}

def update_sync_config(client_id: str, data: dict) -> bool:
    """طھط­ط¯ظٹط« ط¥ط¹ط¯ط§ط¯ط§طھ ط§ظ„ظ…ط²ط§ظ…ظ†ط©"""
    supabase = get_supabase_client()
    try:
        existing = get_sync_config(client_id)
        
        # Ensure connection details are correctly mapped
        connection_details = data.get("connection_details", {})
        
        update_data = {
            "client_id": client_id,
            "source_type": data.get("source_type"),
            "connection_details": connection_details,
            "table_name": data.get("table_name", ""),
            "sheet_name": data.get("sheet_name", ""),
        }
        
        if existing:
            supabase.table("sync_config").update(update_data).eq("client_id", client_id).execute()
        else:
            supabase.table("sync_config").insert(update_data).execute()
            
        return True
    except Exception as e:
        print(f"Error updating sync config: {e}")
        return False
