import os
from dotenv import load_dotenv
load_dotenv()
from database.db_client import get_db_client
import json
supabase = get_db_client()

# get any order id
res = supabase.table("orders").select("id").limit(1).execute()
if res.data:
    order_id = res.data[0]["id"]
    print(f"Testing order_id: {order_id}")
    try:
        order_res = supabase.table("orders").select("*").eq("id", order_id).execute()
        order = order_res.data[0]
        client_id = order.get("client_id")

        # Parse items if it's string
        items = order.get("items", [])
        if isinstance(items, str):
            try:
                import json as _json
                items = _json.loads(items)
            except:
                items = []
        
        if not isinstance(items, list):
            items = [items] if items else []
            
        clean_items = []
        for it in items:
            if isinstance(it, dict):
                clean_items.append(it)
            elif isinstance(it, str):
                clean_items.append({"name": it, "qty": 1, "price": 0})
                
        order["items"] = clean_items

        # Fetch client info for logo
        client_res = supabase.table("clients").select("company_name, logo_url").eq("id", client_id).execute()
        client_info = client_res.data[0] if client_res.data else {}

        print("Dumping JSON:")
        json_data = json.dumps(order, default=str)
        print("Success! No 500 error in data prep.")
    except Exception as e:
        import traceback
        traceback.print_exc()
else:
    print("No orders found")
