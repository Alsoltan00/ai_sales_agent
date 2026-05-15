import sys
import os
sys.path.append(os.getcwd())
from database.db_client import get_supabase_client

supabase = get_supabase_client()
# Get first client id to check
res = supabase.table("clients").select("id").limit(1).execute()
if res.data:
    client_id = res.data[0]["id"]
    plan = supabase.table("planning_config").select("*").eq("client_id", client_id).single().execute()
    print("PLANNING CONFIG:")
    print(plan.data)
    
    rules = supabase.table("business_rules").select("*").eq("client_id", client_id).execute()
    print("BUSINESS RULES:")
    print(rules.data)
