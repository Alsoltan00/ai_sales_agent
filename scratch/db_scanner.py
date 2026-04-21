import os
import requests
import json

# Setup Supabase Connection from current environment
url = "https://pekhtaskywetcohaxpls.supabase.co"
key = "sb_secret_99qNSjvCEOl_z0y1bYV6uQ_NWhlyqWi"
headers = {
    "apikey": key,
    "Authorization": f"Bearer {key}",
    "Content-Type": "application/json"
}

def check_table(table_name):
    full_url = f"{url}/rest/v1/{table_name}?select=*"
    print(f"[*] Checking table: {table_name}")
    try:
        response = requests.get(full_url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"[+] SUCCESS: Table '{table_name}' exists. Count: {len(data)}")
            if data:
                print(f"    Sample Data Keys: {list(data[0].keys())}")
                # Print all found numbers
                for item in data:
                    print(f"    - Found: {item}")
        elif response.status_code == 404:
            print(f"[-] NOT FOUND: Table '{table_name}' does not exist.")
        else:
            print(f"[-] ERROR: Table '{table_name}' returned {response.status_code}")
    except Exception as e:
        print(f"[!] EXCEPTION: {e}")

# Common table names used for whitelists/authorized numbers
candidates = ["white_list", "whitelist", "authorized_numbers", "authorized_users", "allowed_numbers"]

print("--- Supabase Data Search Report ---")
for cand in candidates:
    check_table(cand)
print("----------------------------------")
