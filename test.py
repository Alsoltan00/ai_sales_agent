import os
from dotenv import load_dotenv
load_dotenv()
from supabase import create_client

URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")

print(f"URL: {URL}")
print(f"KEY: {KEY[:15]}...")

try:
    print("Testing create_client...")
    client = create_client(URL, KEY)
    print("Testing insert...")
    res = client.table("products").insert([{"name": "test product"}]).execute()
    print("Success:", res.data)
except Exception as e:
    print("Exception occurred:", type(e))
    print(str(e))
