import os
import requests

def get_supabase_url():
    return os.environ.get("SUPABASE_URL", "").strip()

def get_headers():
    key = os.environ.get("SUPABASE_KEY", "").strip()
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }

def get_store_config(instance_name: str) -> dict | None:
    """
    Fetches store configuration (id, prompt, etc) based on the Evolution instance name.
    """
    url = f"{get_supabase_url()}/rest/v1/stores?evolution_instance_name=eq.{instance_name}&select=*"
    try:
        response = requests.get(url, headers=get_headers())
        if response.status_code == 200:
            stores = response.json()
            return stores[0] if stores else None
    except Exception as e:
        print(f"[!] Error fetching store config: {e}")
    return None

def search_products(keywords: list, store_id: str = None) -> list:
    """
    Search only the local products table (since remote data is synced here every 5 mins).
    """
    if not store_id or not get_supabase_url():
        return []

    base_filter = f"store_id=eq.{store_id}"
    if not keywords:
        query_url = f"{get_supabase_url()}/rest/v1/products?{base_filter}&limit=10"
    else:
        # Search across the name and within the JSON details if possible
        filter_parts = [f"name.ilike.%{kw.strip()}%" for kw in keywords if kw.strip()]
        or_filter = ",".join(filter_parts)
        query_url = f"{get_supabase_url()}/rest/v1/products?{base_filter}&or=({or_filter})&limit=10"
    
    try:
        response = requests.get(query_url, headers=get_headers(), timeout=10)
        return response.json() if response.status_code == 200 else []
    except:
        return []

def delete_store_products(store_id: str):
    """Deletes all products associated with a specific store to allow for a clean re-upload."""
    url = f"{get_supabase_url()}/rest/v1/products?store_id=eq.{store_id}"
    requests.delete(url, headers=get_headers())

def search_live_gsheet(keywords: list, sheet_url: str) -> list:
    """Fetches CSV from Google Sheets and filters in-memory (Live Sync)."""
    import pandas as pd
    import re
    try:
        match = re.search(r"/d/([a-zA-Z0-9-_]+)", sheet_url)
        if not match: return []
        csv_url = f"https://docs.google.com/spreadsheets/d/{match.group(1)}/export?format=csv"
        df = pd.read_csv(csv_url)
        
        # Simple in-memory filtering
        if keywords:
            pattern = '|'.join([re.escape(k) for k in keywords])
            # Search in the first column (usually Name)
            df = df[df.iloc[:, 0].str.contains(pattern, case=False, na=False)]
        
        # Convert to our schema-less format for the LLM
        results = []
        for _, row in df.head(10).iterrows():
            row_dict = row.to_dict()
            name_val = str(row_dict.get(df.columns[0], ""))
            details = {str(k): v for k, v in row_dict.items() if k != df.columns[0] and pd.notna(v)}
            results.append({"name": name_val, "details": details})
        return results
    except: return []

def search_live_external_supabase(keywords: list, config: dict) -> list:
    """Queries an external Supabase REST API directly (Live Sync)."""
    sb_url = config.get("sb_url", "").strip("/")
    sb_key = config.get("sb_key")
    sb_table = config.get("sb_table")
    
    # Construct external query
    ext_url = f"{sb_url}/rest/v1/{sb_table}?select=*"
    if keywords:
        # Try to find a name-like column on the fly or just use 'name'
        ext_url += f"&name.ilike.%{keywords[0]}%" # Assumption for simplicity, can be improved
    
    try:
        res = requests.get(ext_url, headers={"apikey": sb_key, "Authorization": f"Bearer {sb_key}"}, timeout=10)
        if res.status_code == 200:
            data = res.json()
            # Map to our standard format
            return [{"name": item.get("name", "Item"), "details": item} for item in data[:10]]
    except: pass
    return []

def fetch_live_mysql(config: dict) -> tuple:
    """Connects to external MySQL and fetches all data. Returns (list, error_msg)."""
    import mysql.connector
    try:
        conn = mysql.connector.connect(
            host=config.get("host"),
            user=config.get("user"),
            password=config.get("password"),
            database=config.get("db_name"),
            connect_timeout=10
        )
        cursor = conn.cursor(dictionary=True)
        table = config.get("table_name")
        cursor.execute(f"SELECT * FROM {table} LIMIT 1000")
        rows = cursor.fetchall()
        
        results = []
        for row in rows:
            keys = list(row.keys())
            name_key = next((k for k in keys if 'name' in k.lower() or 'اسم' in k), keys[0])
            name_val = str(row.get(name_key, "Item"))
            details = {k: v for k, v in row.items() if k != name_key}
            results.append({"name": name_val, "details": details})
            
        cursor.close()
        conn.close()
        if not results:
            return [], "الجدول موجود ولكن لا يحتوي على بيانات أو لم نتمكن من قراءتها."
        return results, None
    except mysql.connector.Error as err:
        return [], f"خطأ MySQL: {err.msg}"
    except Exception as e:
        return [], f"خطأ في الاتصال: {str(e)}"

def fetch_live_bridge(url: str) -> tuple:
    """Fetches data from a PHP/API bridge URL. Returns (list, error_msg)."""
    import requests
    # Use a browser-like User-Agent to bypass hosting firewalls (like InfinityFree)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code != 200:
            return [], f"فشل الاتصال بالجسر (Status: {res.status_code})"
        
        data = res.json()
        if not isinstance(data, list):
            return [], "تنسيق بيانات الجسر غير صحيح (يجب أن يكون مصفوفة JSON)"
            
        results = []
        for row in data:
            if not isinstance(row, dict): continue
            keys = list(row.keys())
            if not keys: continue
            name_key = next((k for k in keys if 'name' in k.lower() or 'اسم' in k), keys[0])
            name_val = str(row.get(name_key, "Item"))
            details = {k: v for k, v in row.items() if k != name_key}
            results.append({"name": name_val, "details": details})
            
        return results, None
    except Exception as e:
        return [], f"خطأ في قراءة الجسر: {str(e)}"

def check_authorized_number(phone: str, store_id: str = None) -> bool:
    """Checks if a number exists in the authorized_numbers table, scoped by store_id."""
    filter_url = f"phone=eq.{phone}"
    if store_id:
        filter_url += f"&store_id=eq.{store_id}"
        
    url = f"{get_supabase_url()}/rest/v1/authorized_numbers?{filter_url}&select=phone"
    try:
        response = requests.get(url, headers=get_headers())
        if response.status_code == 200:
            return len(response.json()) > 0
    except:
        pass
    return False

def get_all_authorized_numbers(store_id: str = None):
    """Fetches phone numbers from the authorized_numbers table, filtered by store."""
    url = f"{get_supabase_url()}/rest/v1/authorized_numbers?select=phone"
    if store_id:
        url += f"&store_id=eq.{store_id}"
    try:
        response = requests.get(url, headers=get_headers())
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching authorized numbers: {e}")
        return []

def add_authorized_number_db(phone: str, store_id: str = None):
    """Adds a new phone number linked to a specific store."""
    url = f"{get_supabase_url()}/rest/v1/authorized_numbers"
    payload = {"phone": phone}
    if store_id:
        payload["store_id"] = store_id
    requests.post(url, headers=get_headers(), json=payload)

def create_store_db(store_data: dict):
    """Creates a new store entry in Supabase."""
    url = f"{get_supabase_url()}/rest/v1/stores"
    requests.post(url, headers=get_headers(), json=store_data)

def update_store_sync_db(store_id: str, sync_source: str, sync_config: dict):
    """Updates the sync settings for a specific store (Live Sync)."""
    url = f"{get_supabase_url()}/rest/v1/stores?id=eq.{store_id}"
    payload = {
        "sync_source": sync_source,
        "sync_config": sync_config
    }
    requests.patch(url, headers=get_headers(), json=payload)

def delete_authorized_number_db(phone: str):
    """Removes a phone number from the authorized_numbers."""
    url = f"{get_supabase_url()}/rest/v1/authorized_numbers?phone=eq.{phone}"
    requests.delete(url, headers=get_headers())

def upload_products_bulk(products_list: list, store_id: str = None) -> tuple[bool, str]:
    """
    Takes a list of dictionaries and performs a bulk insert into Supabase.
    Includes store_id if provided.
    """
    if store_id:
        for p in products_list:
            p['store_id'] = store_id

    url = f"{get_supabase_url()}/rest/v1/products"
    try:
        if not get_supabase_url():
            return False, "رابط قاعدة البيانات غير مضبوط."
        response = requests.post(url, headers=get_headers(), json=products_list, timeout=30)
        response.raise_for_status()
        return True, "تم الرفع بنجاح"
    except Exception as e:
        return False, f"خطأ في الاتصال: {str(e)}"
