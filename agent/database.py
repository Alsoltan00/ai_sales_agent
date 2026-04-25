"""
=============================================================================
  AI Sales Platform - Multi-Tenant Database Layer (Aiven PostgreSQL)
=============================================================================
  Architecture: PostgreSQL Schema-per-Store isolation.
  
  - 'public' schema: Contains the master 'stores' table only.
  - 'store_{id}' schema: Each store gets its own isolated schema containing:
      * products          - Store's product catalog
      * authorized_numbers - Whitelisted phone numbers
      * settings          - Key/value store-level settings (future use)
      
  This design ensures:
  1. Complete data isolation between stores
  2. Easy future expansion (add tables per store without migrations)
  3. Independent backup/restore per store
  4. No store_id columns needed inside store schemas
=============================================================================
"""

import psycopg2
from psycopg2.extras import RealDictCursor, Json
import json
import requests
import os
import re

# --- AIVEN POSTGRESQL CONFIGURATION ---
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


# =============================================================================
#  SCHEMA & MIGRATION MANAGEMENT
# =============================================================================

def _safe_schema_name(store_id):
    """Generates a safe PostgreSQL schema name from a store ID."""
    clean = re.sub(r'[^a-z0-9_]', '_', str(store_id).lower())
    return f"store_{clean}"

def initialize_database():
    """
    Creates the master 'stores' table in the public schema if it doesn't exist.
    Called once on application startup.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS public.stores (
            id              SERIAL PRIMARY KEY,
            name            TEXT NOT NULL,
            evolution_instance_name TEXT DEFAULT '',
            system_prompt   TEXT DEFAULT '',
            sync_source     TEXT DEFAULT 'local',
            sync_config     JSONB DEFAULT '{}',
            created_at      TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    conn.commit()
    conn.close()
    print("[+] Database initialized: public.stores ready.")

def _create_store_schema(store_id):
    """
    Creates an isolated schema for a specific store with all required tables.
    This is called automatically when a new store is added.
    """
    schema = _safe_schema_name(store_id)
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
    
    # Products catalog
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS "{schema}".products (
            id          SERIAL PRIMARY KEY,
            name        TEXT NOT NULL,
            details     JSONB DEFAULT '{{}}'::jsonb,
            created_at  TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    
    # Authorized phone numbers
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS "{schema}".authorized_numbers (
            id          SERIAL PRIMARY KEY,
            phone       TEXT NOT NULL UNIQUE,
            created_at  TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    
    # Store-level settings (key/value for future expansion)
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS "{schema}".settings (
            key         TEXT PRIMARY KEY,
            value       TEXT DEFAULT ''
        )
    """)
    
    conn.commit()
    conn.close()
    print(f"[+] Schema '{schema}' created with all tables.")


# =============================================================================
#  STORE MANAGEMENT (public schema)
# =============================================================================

def create_store(name: str, instance_name: str = "", system_prompt: str = ""):
    """Creates a new store and its isolated schema."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO public.stores (name, evolution_instance_name, system_prompt, sync_source, sync_config)
           VALUES (%s, %s, %s, 'local', '{}')
           RETURNING id""",
        (name, instance_name, system_prompt)
    )
    store_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    
    # Create isolated schema for this store
    _create_store_schema(store_id)
    return store_id

def fetch_stores():
    """Fetches all stores from the master table."""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM public.stores ORDER BY id")
    stores = cursor.fetchall()
    conn.close()
    
    # Convert RealDictRow to regular dict for template compatibility
    return [dict(s) for s in stores]

def fetch_store_by_id(store_id):
    """Fetches a specific store by ID."""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM public.stores WHERE id = %s", (store_id,))
    store = cursor.fetchone()
    conn.close()
    return dict(store) if store else None

def update_store(store_id, name: str = None, instance_name: str = None, system_prompt: str = None):
    """Updates store details."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    updates = []
    params = []
    if name is not None:
        updates.append("name = %s")
        params.append(name)
    if instance_name is not None:
        updates.append("evolution_instance_name = %s")
        params.append(instance_name)
    if system_prompt is not None:
        updates.append("system_prompt = %s")
        params.append(system_prompt)
    
    if updates:
        params.append(store_id)
        cursor.execute(f"UPDATE public.stores SET {', '.join(updates)} WHERE id = %s", params)
        conn.commit()
    conn.close()

def delete_store(store_id):
    """Deletes a store and its entire isolated schema."""
    schema = _safe_schema_name(store_id)
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Drop the entire schema (all store data gone)
    cursor.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
    # Remove from master table
    cursor.execute("DELETE FROM public.stores WHERE id = %s", (store_id,))
    
    conn.commit()
    conn.close()
    print(f"[+] Store {store_id} and schema '{schema}' deleted.")

def update_store_sync_db(store_id, source: str, config: dict):
    """Updates the sync source and config for a store."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE public.stores SET sync_source = %s, sync_config = %s WHERE id = %s",
        (source, Json(config), store_id)
    )
    conn.commit()
    conn.close()


# =============================================================================
#  PRODUCT OPERATIONS (store-isolated schema)
# =============================================================================

def fetch_products_by_store(store_id):
    """Fetches all products from a store's isolated schema."""
    schema = _safe_schema_name(store_id)
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(f'SELECT * FROM "{schema}".products ORDER BY id')
        products = cursor.fetchall()
        return [dict(p) for p in products]
    except Exception as e:
        print(f"[!] fetch_products error for store {store_id}: {e}")
        return []
    finally:
        conn.close()

def delete_store_products(store_id):
    """Purges all products in a store's schema."""
    schema = _safe_schema_name(store_id)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f'DELETE FROM "{schema}".products')
        conn.commit()
    except Exception as e:
        print(f"[!] delete_products error: {e}")
        conn.rollback()
    finally:
        conn.close()

def upload_products_bulk(products: list, store_id):
    """Uploads a list of products into a store's isolated schema."""
    schema = _safe_schema_name(store_id)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        for p in products:
            details = p.get("details", {})
            if isinstance(details, str):
                try: details = json.loads(details)
                except: details = {"raw": details}
            cursor.execute(
                f'INSERT INTO "{schema}".products (name, details) VALUES (%s, %s)',
                (p.get("name", ""), Json(details))
            )
        conn.commit()
    except Exception as e:
        print(f"[!] upload_products error: {e}")
        conn.rollback()
    finally:
        conn.close()

def search_products(keywords: list, store_id):
    """Searches products by keywords within a store's isolated schema."""
    if not keywords:
        return fetch_products_by_store(store_id)
    
    schema = _safe_schema_name(store_id)
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    query_parts = []
    params = []
    for kw in keywords:
        query_parts.append("(name ILIKE %s OR details::text ILIKE %s)")
        params.extend([f"%{kw}%", f"%{kw}%"])
    
    where_clause = " AND ".join(query_parts)
    
    try:
        cursor.execute(f'SELECT * FROM "{schema}".products WHERE {where_clause}', params)
        return [dict(p) for p in cursor.fetchall()]
    except Exception as e:
        print(f"[!] search_products error: {e}")
        return []
    finally:
        conn.close()


# =============================================================================
#  AUTHORIZED NUMBERS (store-isolated schema)
# =============================================================================

def fetch_authorized_numbers(store_id):
    """Fetches all authorized numbers for a store."""
    schema = _safe_schema_name(store_id)
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(f'SELECT * FROM "{schema}".authorized_numbers ORDER BY id')
        return [dict(n) for n in cursor.fetchall()]
    except Exception as e:
        print(f"[!] fetch_numbers error: {e}")
        return []
    finally:
        conn.close()

def add_authorized_number(phone: str, store_id):
    """Adds a phone number to a store's whitelist."""
    schema = _safe_schema_name(store_id)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            f'INSERT INTO "{schema}".authorized_numbers (phone) VALUES (%s) ON CONFLICT (phone) DO NOTHING',
            (phone,)
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"[!] add_number error: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def delete_authorized_number(phone: str, store_id):
    """Removes a phone number from a store's whitelist."""
    schema = _safe_schema_name(store_id)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f'DELETE FROM "{schema}".authorized_numbers WHERE phone = %s', (phone,))
        conn.commit()
        return True
    except Exception as e:
        print(f"[!] delete_number error: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def check_authorized_number(clean_number: str, store_id):
    """Checks if a number is whitelisted for a store. If no numbers exist, allow all."""
    schema = _safe_schema_name(store_id)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # If no numbers registered, allow everyone (open mode)
        cursor.execute(f'SELECT COUNT(*) FROM "{schema}".authorized_numbers')
        total = cursor.fetchone()[0]
        if total == 0:
            return True
        
        # Check if this specific number is whitelisted
        cursor.execute(
            f'SELECT COUNT(*) FROM "{schema}".authorized_numbers WHERE phone = %s',
            (clean_number,)
        )
        return cursor.fetchone()[0] > 0
    except Exception as e:
        print(f"[!] check_number error: {e}")
        return True  # Fail-open on errors
    finally:
        conn.close()


# =============================================================================
#  STORE CONFIG FOR CONVERSATION MANAGER
# =============================================================================

def get_store_config(instance_name: str):
    """Fetches store configuration by Evolution instance name."""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Try matching by instance name first, then by store name
    cursor.execute(
        "SELECT * FROM public.stores WHERE evolution_instance_name = %s OR name = %s LIMIT 1",
        (instance_name, instance_name)
    )
    store = cursor.fetchone()
    conn.close()
    
    if store:
        return {
            "id": str(store["id"]),
            "name": store["name"],
            "system_prompt": store.get("system_prompt", ""),
            "evolution_instance_name": store.get("evolution_instance_name", "")
        }
    return None


# =============================================================================
#  DATA MIGRATION: Old flat tables → New schema-based isolation
# =============================================================================

def migrate_old_data():
    """
    One-time migration: moves data from old flat 'products' table
    into the new per-store schemas. Safe to run multiple times.
    """
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Check if old products table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = 'products'
            )
        """)
        if not cursor.fetchone()["exists"]:
            return  # No old data to migrate
        
        print("[*] Migrating old flat data to schema-based isolation...")
        
        # Get all stores
        cursor.execute("SELECT * FROM public.stores")
        stores = cursor.fetchall()
        
        for store in stores:
            store_id = store["id"]
            schema = _safe_schema_name(store_id)
            
            # Ensure schema exists
            _create_store_schema(store_id)
            
            # Move products
            cursor.execute(
                "SELECT name, details FROM public.products WHERE store_id = %s",
                (str(store_id),)
            )
            products = cursor.fetchall()
            
            if products:
                for p in products:
                    cursor.execute(
                        f'INSERT INTO "{schema}".products (name, details) VALUES (%s, %s)',
                        (p["name"], Json(p["details"]) if isinstance(p["details"], dict) else p["details"])
                    )
                print(f"  [+] Migrated {len(products)} products for store {store_id}")
        
        # Rename old table to mark as migrated (don't delete yet)
        cursor.execute("ALTER TABLE public.products RENAME TO products_old_backup")
        conn.commit()
        print("[+] Migration complete! Old table renamed to 'products_old_backup'.")
        
    except Exception as e:
        print(f"[!] Migration error (non-fatal): {e}")
        conn.rollback()
    finally:
        conn.close()


# =============================================================================
#  EXTERNAL SOURCE FETCHERS (unchanged, source-agnostic)
# =============================================================================

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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
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
