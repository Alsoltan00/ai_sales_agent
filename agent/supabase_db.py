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
    Given a list of keywords extracted by the LLM Intent Analyzer, 
    this searches the 'products' table in Supabase for matches using direct REST API.
    """
    if not keywords:
        return []

    main_kw = f"%{keywords[0]}%"
    
    # Construct an ILIKE filter for the REST API
    # Search in name, barcode, unit, and package
    query_str = f"or=(name.ilike.{main_kw},barcode.ilike.{main_kw},unit.ilike.{main_kw},package.ilike.{main_kw})&limit=10"
    
    url = f"{get_supabase_url()}/rest/v1/products?{query_str}"
    
    try:
        if not get_supabase_url():
            raise Exception("Supabase URL is not configured.")
        response = requests.get(url, headers=get_headers(), timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"[!] Supabase Search Error: {e}")
        return []

def upload_products_bulk(products_list: list) -> tuple[bool, str]:
    """
    Takes a list of dictionaries and performs a bulk insert into Supabase via REST API.
    Returns (success_boolean, error_message).
    """
    url = f"{get_supabase_url()}/rest/v1/products"
    
    try:
        if not get_supabase_url():
            return False, "رابط قاعدة البيانات (Supabase URL) غير مضبوط في الإعدادات."
            
        print(f"[*] Sending {len(products_list)} products to Supabase...")
        response = requests.post(url, headers=get_headers(), json=products_list, timeout=30)
        response.raise_for_status()
        print(f"[+] Successfully inserted products into Supabase.")
        return True, "تم الرفع بنجاح"
    except requests.exceptions.HTTPError as err:
        error_details = err.response.text
        print(f"[!] Bulk Insert HTTP Error: {error_details}")
        return False, f"خطأ في قاعدة البيانات: {error_details}"
    except Exception as e:
        print(f"[!] Bulk Insert Error: {e}")
        return False, f"خطأ في الاتصال: {str(e)}"
