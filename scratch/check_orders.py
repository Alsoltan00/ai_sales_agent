import os
from dotenv import load_dotenv
load_dotenv()
from database.db_client import get_supabase_client

supabase = get_supabase_client()
# Get all orders
try:
    res = supabase.table("orders").select("*").execute()
    orders = res.data or []
    print(f"Fetched {len(orders)} orders.")
    
    # Check for None total_amount
    bad_totals = [o for o in orders if o.get('total_amount') is None]
    print(f"Orders with None total_amount: {len(bad_totals)}")
    
    # Check for items parsing
    bad_items = []
    for o in orders:
        if isinstance(o.get('items'), str):
            bad_items.append(o)
    print(f"Orders with items as string (instead of dict/list): {len(bad_items)}")

    # Check for None values in stats sum
    none_orders = [o for o in orders if o.get('total_amount') is None]
    if none_orders:
        print("Found None total_amounts:")
        for no in none_orders:
            print(no)

except Exception as e:
    print(f"Error: {e}")
