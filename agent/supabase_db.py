import psycopg2
from psycopg2.extras import RealDictCursor, Json
import json
import requests
import os

# --- AIVEN POSTGRESQL CONFIGURATION (Using Environment Variables for Security) ---
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "pg-28be3d8d-asillalsoltan74-d568.c.aivencloud.com"),
    "port": os.getenv("DB_PORT", "27013"),
    "user": os.getenv("DB_USER", "avnadmin"),
    "password": os.getenv("DB_PASS"),
    "database": os.getenv("DB_NAME", "defaultdb"),
    "sslmode": "require"
}

def get_db_connection():
    """Establishes a connection to the Aiven PostgreSQL database."""
    return psycopg2.connect(**DB_CONFIG)

# --- DATABASE OPERATIONS (REPLACING SUPABASE REST) ---

def fetch_stores():
    """Fetches all stores from the PostgreSQL database."""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM stores")
    stores = cursor.fetchall()
    conn.close()
    return stores

def fetch_store_by_id(store_id: str):
    """Fetches a specific store by ID."""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM stores WHERE id = %s", (store_id,))
    store = cursor.fetchone()
    conn.close()
    return store

def update_store_sync_db(store_id: str, source: str, config: dict):
    """Updates the sync source and config for a store."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE stores SET sync_source = %s, sync_config = %s WHERE id = %s",
        (source, Json(config), store_id)
    )
    conn.commit()
    conn.close()

def delete_store_products(store_id: str):
    """Purges all products for a specific store."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM products WHERE store_id = %s", (store_id,))
    conn.commit()
    conn.close()

def upload_products_bulk(products: list, store_id: str):
    """Uploads a list of products to the PostgreSQL database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    for p in products:
        cursor.execute(
            "INSERT INTO products (store_id, name, details) VALUES (%s, %s, %s)",
            (store_id, p["name"], Json(p["details"]))
        )
    conn.commit()
    conn.close()

def fetch_products_by_store(store_id: str):
    """Fetches all products for a specific store."""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM products WHERE store_id = %s", (store_id,))
    products = cursor.fetchall()
    conn.close()
    return products

# --- EXTERNAL SOURCE FETCHERS (RETAINED) ---

def search_live_gsheet(query_keywords, sheet_url):
    """Fetches data from Google Sheets (CSV Export) without heavy dependencies."""
    if not sheet_url: return []
    csv_url = sheet_url.replace('/edit?usp=sharing', '/export?format=csv').replace('/edit#gid=', '/export?format=csv&gid=')
    if '/export?format=csv' not in csv_url: csv_url += '/export?format=csv'
    
    try:
        import csv
        import urllib.request
        import io
        
        req = urllib.request.Request(csv_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            csv_data = response.read().decode('utf-8')
            
        reader = csv.DictReader(io.StringIO(csv_data))
        results = []
        for row in reader:
            if not row: continue
            name_key = next((k for k in row.keys() if k and ('name' in k.lower() or 'اسم' in k)), list(row.keys())[0])
            name = str(row[name_key])
            details = {k: str(v) for k, v in row.items() if k != name_key}
            results.append({"name": name, "details": details})
        return results
    except Exception as e:
        print(f"GSheet Error: {e}")
        return []

def search_live_external_supabase(query_keywords, config):
    """Fetches data from an external Supabase instance."""
    url = f"{config.get('url')}/rest/v1/{config.get('table')}?select=*"
    headers = {
        "apikey": config.get("key"),
        "Authorization": f"Bearer {config.get('key')}"
    }
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            data = res.json()
            results = []
            for item in data:
                name_key = next((k for k in item.keys() if 'name' in k.lower() or 'اسم' in k), list(item.keys())[0])
                name = str(item[name_key])
                details = {k: str(v) for k, v in item.items() if k != name_key}
                results.append({"name": name, "details": details})
            return results
    except: pass
    return []

def fetch_live_mysql(config):
    """Fetches data from a remote MySQL database."""
    import mysql.connector
    try:
        conn = mysql.connector.connect(
            host=config.get("host"),
            user=config.get("user"),
            password=config.get("password"),
            database=config.get("database"),
            connect_timeout=10
        )
        cursor = conn.cursor(dictionary=True)
        table = config.get("table", "products")
        cursor.execute(f"SELECT * FROM {table} LIMIT 1000")
        rows = cursor.fetchall()
        conn.close()
        
        results = []
        for row in rows:
            name_key = next((k for k in row.keys() if 'name' in k.lower() or 'اسم' in k), list(row.keys())[0])
            name = str(row[name_key])
            details = {k: str(v) for k, v in row.items() if k != name_key}
            results.append({"name": name, "details": details})
        return results, None
    except Exception as e:
        return [], str(e)

def fetch_live_bridge(url: str) -> tuple:
    """Fetches data from a PHP/API bridge URL."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code != 200:
            return [], f"فشل الاتصال بالجسر (Status: {res.status_code})"
        
        data = res.json()
        if isinstance(data, dict) and "error" in data:
            return [], data["error"]
            
        results = []
        for row in data:
            if not isinstance(row, dict): continue
            name_key = next((k for k in row.keys() if 'name' in k.lower() or 'اسم' in k), list(row.keys())[0])
            name = str(row[name_key])
            details = {k: str(v) for k, v in row.items() if k != name_key}
            results.append({"name": name, "details": details})
        return results, None
    except Exception as e:
        return [], f"خطأ في قراءة الجسر: {str(e)}"
