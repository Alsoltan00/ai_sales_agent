import os
from database.db_client import get_supabase_client
import bcrypt

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        if not hashed_password:
            return False
        # Truncate to match registration logic
        safe_password = plain_password.encode('utf-8')[:50]
        # Check if the hashed_password is a valid bcrypt hash
        return bcrypt.checkpw(safe_password, hashed_password.encode('utf-8'))
    except Exception as e:
        print(f"Bcrypt verification error: {e}")
        # Fallback for plain text passwords (not recommended for production but kept for migration)
        return plain_password == hashed_password

def authenticate_user(contact_info: str, password: str) -> dict | None:
    """
    يتحقق من بيانات الدخول
    1. يبحث في جدول users (الموظفين)
    2. إن لم يجد، يبحث في جدول clients (العملاء)
    """
    supabase = get_supabase_client()
    
    # 1. البحث في جدول الموظفين
    # نفترض أن contact_info هو الإيميل للموظف
    try:
        response = supabase.table("sales_admin_users").select("*").eq("email", contact_info).execute()
        if response.data:
            user = response.data[0]
            if verify_password(password, user.get("password_hash", "")):
                import json
                perms = user.get("permissions", {})
                if isinstance(perms, str):
                    try:
                        perms = json.loads(perms)
                    except:
                        perms = {}
                return {
                    "id": user["id"],
                    "name": user.get("name", "مدير"),
                    "user_type": "admin_user",
                    "permissions": perms
                }
    except Exception as e:
        print(f"Error checking users table: {e}")

    # 2. البحث في جدول العملاء
    # قد يكون الإيميل أو رقم التواصل
    try:
        response = supabase.table("clients").select("*").eq("contact_number", contact_info).execute()
        if not response.data:
            response = supabase.table("clients").select("*").eq("email", contact_info).execute()
            
        if response.data:
            client = response.data[0]
            if client.get("status") != "active":
                return None # الحساب ليس فعالاً
                
            if verify_password(password, client.get("password_hash", "")):
                return {
                    "id": client["id"],
                    "name": client.get("company_name", "تاجر"),
                    "user_type": "merchant",
                    "permissions": {}
                }
    except Exception as e:
        print(f"Error checking clients table: {e}")

    return None
