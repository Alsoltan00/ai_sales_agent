import sys
import os
sys.path.append(os.getcwd())
from database.db_client import get_supabase_client

supabase = get_supabase_client()
res = supabase.table("orders").select("id, order_number, total_amount, created_at").order("created_at", desc=True).limit(5).execute()
print("LAST 5 ORDERS:")
for r in res.data:
    print(r)
