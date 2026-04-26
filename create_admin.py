import json
from database.db_client import get_db_client

def create_admin():
    db = get_db_client()
    
    email = "admin@ai-sales.com"
    password = "admin"
    
    perms = json.dumps({
        "can_manage_new_clients": True,
        "can_manage_subscriptions": True,
        "can_manage_users": True,
        "is_admin": True
    })

    # Check if admin exists
    existing = db.table("sales_admin_users").select("*").eq("email", email).execute()
    if existing.data:
        print("Admin user already exists!")
    else:
        db.table("sales_admin_users").insert({
            "name": "Super Admin",
            "email": email,
            "password_hash": password,  # Fallback to plain text for ease
            "permissions": perms
        }).execute()
        print("Admin user created successfully!")
        
    # Also create a demo merchant
    merchant_phone = "123456789"
    merchant_pass = "merchant"
    existing_merchant = db.table("clients").select("*").eq("contact_number", merchant_phone).execute()
    if existing_merchant.data:
        print("Demo merchant already exists!")
    else:
        db.table("clients").insert({
            "company_name": "متجر الأمل",
            "contact_number": merchant_phone,
            "email": "merchant@ai-sales.com",
            "password_hash": merchant_pass,
            "status": "active"
        }).execute()
        print("Demo merchant created successfully!")

if __name__ == "__main__":
    create_admin()
