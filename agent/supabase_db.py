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

def search_products(keywords: list) -> list:
    """
    Upgraded: Searches the 'products' table for matches across multiple keywords using OR logic.
    """
    if not keywords:
        # Show some random products if no keywords (general inquiry)
        url = f"{get_supabase_url()}/rest/v1/products?limit=10"
    else:
        # Construct a multi-keyword OR filter across name, barcode, unit, and package
        filter_parts = []
        for kw in keywords:
            kw_clean = kw.strip()
            if kw_clean:
                filter_parts.append(f"name.ilike.%{kw_clean}%,barcode.ilike.%{kw_clean}%,unit.ilike.%{kw_clean}%,package.ilike.%{kw_clean}%")
        
        or_filter = ",".join(filter_parts)
        url = f"{get_supabase_url()}/rest/v1/products?or=({or_filter})&limit=10"
    
    try:
        if not get_supabase_url():
            return []
        response = requests.get(url, headers=get_headers(), timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"[!] Supabase Search Error: {e}")
        return []

def check_authorized_number(phone: str) -> bool:
    """Checks if a number exists in the authorized_numbers table (Supabase)."""
    url = f"{get_supabase_url()}/rest/v1/authorized_numbers?phone=eq.{phone}&select=phone"
    try:
        response = requests.get(url, headers=get_headers())
        if response.status_code == 200:
            return len(response.json()) > 0
    except:
        pass
    return False

def get_all_authorized_numbers():
    """Fetches all phone numbers from the authorized_numbers table."""
    url = f"{get_supabase_url()}/rest/v1/authorized_numbers?select=phone"
    try:
        response = requests.get(url, headers=get_headers())
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching authorized numbers: {e}")
        return []

def add_authorized_number_db(phone: str):
    """Adds a new phone number to the authorized_numbers."""
    url = f"{get_supabase_url()}/rest/v1/authorized_numbers"
    requests.post(url, headers=get_headers(), json={"phone": phone})

def delete_authorized_number_db(phone: str):
    """Removes a phone number from the authorized_numbers."""
    url = f"{get_supabase_url()}/rest/v1/authorized_numbers?phone=eq.{phone}"
    requests.delete(url, headers=get_headers())

def upload_products_bulk(products_list: list) -> tuple[bool, str]:
    """
    Takes a list of dictionaries and performs a bulk insert into Supabase via REST API.
    """
    url = f"{get_supabase_url()}/rest/v1/products"
    try:
        if not get_supabase_url():
            return False, "رابط قاعدة البيانات غير مضبوط."
        response = requests.post(url, headers=get_headers(), json=products_list, timeout=30)
        response.raise_for_status()
        return True, "تم الرفع بنجاح"
    except Exception as e:
        return False, f"خطأ في الاتصال: {str(e)}"
