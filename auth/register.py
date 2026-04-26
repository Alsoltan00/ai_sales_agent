from database.db_client import get_supabase_client

def check_existing_account(contact_number: str) -> bool:
    """ظٹطھط­ظ‚ظ‚ ظ…ظ…ط§ ط¥ط°ط§ ظƒط§ظ† ط§ظ„ط±ظ‚ظ… ظ…ط³ط¬ظ„ط§ظ‹ ط¨ط§ظ„ظپط¹ظ„ ظƒط¹ظ…ظٹظ„ ط£ظˆ ط·ظ„ط¨ ظ‚ظٹط¯ ط§ظ„ط§ظ†طھط¸ط§ط±"""
    supabase = get_supabase_client()
    try:
        # Check in active clients
        res_clients = supabase.table("clients").select("id").eq("contact_number", contact_number).execute()
        if res_clients.data:
            return True
            
        # Check in pending requests
        res_requests = supabase.table("new_client_requests").select("id").eq("contact_number", contact_number).execute()
        if res_requests.data:
            return True
            
    except Exception as e:
        print(f"Error checking existing account: {e}")
        
    return False

def register_new_client(company_name: str, contact_number: str) -> tuple[bool, str]:
    """
    ظٹط³ط¬ظ„ ط·ظ„ط¨ ط¹ظ…ظٹظ„ ط¬ط¯ظٹط¯
    ظٹط¹ظٹط¯ (Success_boolean, Message)
    """
    if not company_name or not contact_number:
        return False, "ظٹط¬ط¨ ط¥ط¯ط®ط§ظ„ ط§ط³ظ… ط§ظ„ط´ط±ظƒط© ظˆط±ظ‚ظ… ط§ظ„طھظˆط§طµظ„"
        
    if check_existing_account(contact_number):
        return False, "ظ‡ط°ط§ ط§ظ„ط±ظ‚ظ… ظ…ط³ط¬ظ„ ط¨ط§ظ„ظپط¹ظ„طŒ ظٹط±ط¬ظ‰ طھط³ط¬ظٹظ„ ط§ظ„ط¯ط®ظˆظ„"
        
    supabase = get_supabase_client()
    try:
        data = {
            "company_name": company_name,
            "contact_number": contact_number,
            "status": "pending"
        }
        supabase.table("new_client_requests").insert(data).execute()
        return True, "طھظ… طھط³ط¬ظٹظ„ ط·ظ„ط¨ظƒ ط¨ظ†ط¬ط§ط­طŒ ط³ظٹطھظ… ظ…ط±ط§ط¬ط¹طھظ‡ ظ…ظ† ظ‚ط¨ظ„ ط§ظ„ط¥ط¯ط§ط±ط©"
    except Exception as e:
        print(f"Error registering new client: {e}")
        return False, "ط­ط¯ط« ط®ط·ط£ ط£ط«ظ†ط§ط، ط¥ط±ط³ط§ظ„ ط§ظ„ط·ظ„ط¨طŒ ظٹط±ط¬ظ‰ ط§ظ„ظ…ط­ط§ظˆظ„ط© ظ„ط§ط­ظ‚ط§ظ‹"
