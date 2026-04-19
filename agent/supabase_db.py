import os
import requests

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

def get_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
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
    url = f"{SUPABASE_URL}/rest/v1/products?{query_str}"
    
    try:
        response = requests.get(url, headers=get_headers())
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"[!] Supabase Search Error: {e}")
        return []

def upload_products_bulk(products_list: list) -> bool:
    """
    Takes a list of dictionaries and performs a bulk insert into Supabase via REST API.
    """
    url = f"{SUPABASE_URL}/rest/v1/products"
    
    try:
        response = requests.post(url, headers=get_headers(), json=products_list)
        response.raise_for_status()
        print(f"[+] Successfully inserted products into Supabase.")
        return True
    except requests.exceptions.HTTPError as err:
        print(f"[!] Bulk Insert HTTP Error: {err.response.text}")
        return False
    except Exception as e:
        print(f"[!] Bulk Insert Error: {e}")
        return False
