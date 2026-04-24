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
    Intelligent Hybrid Search:
    Decides whether to search locally or fetch live data (Google Sheets / External Supabase)
    based on the store's sync_source setting.
    """
    if not store_id:
        return []

    # 1. Fetch Store Sync Configuration
    url = f"{get_supabase_url()}/rest/v1/stores?id=eq.{store_id}&select=sync_source,sync_config"
    try:
        res = requests.get(url, headers=get_headers())
        store_settings = res.json()[0] if res.status_code == 200 and res.json() else {}
    except:
        store_settings = {"sync_source": "local"}

    source = store_settings.get("sync_source", "local")
    config = store_settings.get("sync_config", {})

    # --- CASE A: LIVE GOOGLE SHEETS SEARCH ---
    if source == "gsheet" and config.get("url"):
        return search_live_gsheet(keywords, config.get("url"))

    # --- CASE B: LIVE EXTERNAL SUPABASE SEARCH ---
    elif source == "supabase" and config.get("sb_url"):
        return search_live_external_supabase(keywords, config)

    # --- CASE C: LOCAL DATABASE SEARCH (DEFAULT) ---
    else:
        base_filter = f"store_id=eq.{store_id}"
        if not keywords:
            query_url = f"{get_supabase_url()}/rest/v1/products?{base_filter}&limit=10"
        else:
            filter_parts = [f"name.ilike.%{kw.strip()}%" for kw in keywords if kw.strip()]
            or_filter = ",".join(filter_parts)
            query_url = f"{get_supabase_url()}/rest/v1/products?{base_filter}&or=({or_filter})&limit=10"
        
        try:
            response = requests.get(query_url, headers=get_headers(), timeout=10)
            return response.json() if response.status_code == 200 else []
        except:
            return []

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
