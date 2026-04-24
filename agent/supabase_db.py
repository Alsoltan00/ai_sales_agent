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
    Upgraded: Searches the 'products' table for matches across multiple keywords, 
    scoped to a specific store_id.
    """
    if not get_supabase_url():
        return []

    base_filter = ""
    if store_id:
        base_filter = f"store_id=eq.{store_id}"

    if not keywords:
        url = f"{get_supabase_url()}/rest/v1/products?{base_filter}&limit=10"
    else:
        filter_parts = []
        for kw in keywords:
            kw_clean = kw.strip()
            if kw_clean:
                filter_parts.append(f"name.ilike.%{kw_clean}%,barcode.ilike.%{kw_clean}%,unit.ilike.%{kw_clean}%,package.ilike.%{kw_clean}%")
        
        or_filter = ",".join(filter_parts)
        url = f"{get_supabase_url()}/rest/v1/products?{base_filter}&or=({or_filter})&limit=10"
    
    try:
        response = requests.get(url, headers=get_headers(), timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"[!] Supabase Search Error: {e}")
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
