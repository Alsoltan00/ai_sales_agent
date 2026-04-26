from database.db_client import get_supabase_client

def get_authorized_numbers(client_id: str) -> list:
    """ط¬ظ„ط¨ ط¬ظ…ظٹط¹ ط§ظ„ط£ط±ظ‚ط§ظ… ط§ظ„ظ…طµط±ط­ط© ظ„ط¹ظ…ظٹظ„ ظ…ط¹ظٹظ†"""
    supabase = get_supabase_client()
    try:
        res = supabase.table("authorized_numbers").select("*").eq("client_id", client_id).execute()
        return res.data if res.data else []
    except Exception as e:
        print(f"Error fetching authorized numbers: {e}")
        return []

def add_authorized_number(client_id: str, phone_number: str, label: str = "") -> bool:
    """ط¥ط¶ط§ظپط© ط±ظ‚ظ… ظ…طµط±ط­ ط¬ط¯ظٹط¯"""
    supabase = get_supabase_client()
    try:
        data = {
            "client_id": client_id,
            "phone_number": phone_number,
            "label": label
        }
        supabase.table("authorized_numbers").insert(data).execute()
        return True
    except Exception as e:
        print(f"Error adding authorized number: {e}")
        return False

def delete_authorized_number(client_id: str, record_id: str) -> bool:
    """ط­ط°ظپ ط±ظ‚ظ… ظ…طµط±ط­"""
    supabase = get_supabase_client()
    try:
        supabase.table("authorized_numbers").delete().eq("id", record_id).eq("client_id", client_id).execute()
        return True
    except Exception as e:
        print(f"Error deleting authorized number: {e}")
        return False

def set_allow_all(client_id: str, allow_all: bool) -> bool:
    """طھظپط¹ظٹظ„ ط£ظˆ طھط¹ط·ظٹظ„ ط§ظ„ط±ط¯ ط¹ظ„ظ‰ ط§ظ„ط¬ظ…ظٹط¹"""
    supabase = get_supabase_client()
    try:
        # We store allow_all config in clients table as it's a global setting for the client
        supabase.table("clients").update({"allow_all_numbers": allow_all}).eq("id", client_id).execute()
        return True
    except Exception as e:
        print(f"Error setting allow_all: {e}")
        return False

def get_allow_all_status(client_id: str) -> bool:
    supabase = get_supabase_client()
    try:
        res = supabase.table("clients").select("allow_all_numbers").eq("id", client_id).single().execute()
        return res.data.get("allow_all_numbers", False) if res.data else False
    except:
        return False
