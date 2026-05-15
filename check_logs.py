import sys
import os
sys.path.append(os.getcwd())
from database.db_client import get_supabase_client

supabase = get_supabase_client()
res = supabase.table("message_logs").select("*").order("timestamp", desc=True).limit(5).execute()
for r in res.data:
    print("USER:", r.get('message_text'))
    print("AI REPLY:", r.get('ai_response'))
    print("-" * 50)
