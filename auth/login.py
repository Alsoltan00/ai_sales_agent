import os
from database.db_client import get_supabase_client
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        # Fallback for plain text passwords or different hashes during migration
        return plain_password == hashed_password

def authenticate_user(contact_info: str, password: str) -> dict | None:
    """
    ظٹطھط­ظ‚ظ‚ ظ…ظ† ط¨ظٹط§ظ†ط§طھ ط§ظ„ط¯ط®ظˆظ„
    1. ظٹط¨ط­ط« ظپظٹ ط¬ط¯ظˆظ„ users (ط§ظ„ظ…ظˆط¸ظپظٹظ†)
    2. ط¥ظ† ظ„ظ… ظٹط¬ط¯طŒ ظٹط¨ط­ط« ظپظٹ ط¬ط¯ظˆظ„ clients (ط§ظ„ط¹ظ…ظ„ط§ط،)
    """
    supabase = get_supabase_client()
    
    # 1. ط§ظ„ط¨ط­ط« ظپظٹ ط¬ط¯ظˆظ„ ط§ظ„ظ…ظˆط¸ظپظٹظ†
    # ظ†ظپطھط±ط¶ ط£ظ† contact_info ظ‡ظˆ ط§ظ„ط¥ظٹظ…ظٹظ„ ظ„ظ„ظ…ظˆط¸ظپ
    try:
        response = supabase.table("sales_admin_users").select("*").eq("email", contact_info).execute()
        if response.data:
            user = response.data[0]
            if verify_password(password, user.get("password_hash", "")):
                return {
                    "id": user["id"],
                    "name": user.get("name", "ظ…ط¯ظٹط±"),
                    "user_type": "admin_user",
                    "permissions": user.get("permissions", {})
                }
    except Exception as e:
        print(f"Error checking users table: {e}")

    # 2. ط§ظ„ط¨ط­ط« ظپظٹ ط¬ط¯ظˆظ„ ط§ظ„ط¹ظ…ظ„ط§ط،
    # ظ‚ط¯ ظٹظƒظˆظ† ط§ظ„ط¥ظٹظ…ظٹظ„ ط£ظˆ ط±ظ‚ظ… ط§ظ„طھظˆط§طµظ„
    try:
        response = supabase.table("clients").select("*").eq("contact_number", contact_info).execute()
        if not response.data:
            response = supabase.table("clients").select("*").eq("email", contact_info).execute()
            
        if response.data:
            client = response.data[0]
            if client.get("status") != "active":
                return None # ط§ظ„ط­ط³ط§ط¨ ظ„ظٹط³ ظپط¹ط§ظ„ط§ظ‹
                
            if verify_password(password, client.get("password_hash", "")):
                return {
                    "id": client["id"],
                    "name": client.get("company_name", "طھط§ط¬ط±"),
                    "user_type": "merchant",
                    "permissions": {}
                }
    except Exception as e:
        print(f"Error checking clients table: {e}")

    return None
