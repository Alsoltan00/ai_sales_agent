import os
from database.db_client import get_supabase_client

db = get_supabase_client()
try:
    res = db.table("clients").select("*").execute()
    print("Clients data:")
    print(res.data)
except Exception as e:
    print(f"Error: {e}")
