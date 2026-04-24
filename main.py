import os
import json
import asyncio
import logging
from typing import List, Optional
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException, Header
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from agent.evolution_api import handle_incoming_message
import requests

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# --- UTILS & DATABASE OPERATIONS ---

def get_store_config(store_id: str):
    """Fetches store configuration from Supabase."""
    from agent.supabase_db import get_supabase_url, get_headers
    url = f"{get_supabase_url()}/rest/v1/stores?id=eq.{store_id}&select=*"
    res = requests.get(url, headers=get_headers())
    if res.status_code == 200 and res.json():
        return res.json()[0]
    return None

def delete_store_products(store_id: str):
    """Purges all products for a specific store."""
    from agent.supabase_db import get_supabase_url, get_headers
    url = f"{get_supabase_url()}/rest/v1/products?store_id=eq.{store_id}"
    requests.delete(url, headers=get_headers())

def upload_products_bulk(products: List[dict], store_id: str):
    """Uploads a list of products to Supabase."""
    from agent.supabase_db import get_supabase_url, get_headers
    url = f"{get_supabase_url()}/rest/v1/products"
    headers = get_headers()
    headers["Prefer"] = "return=representation"
    requests.post(url, json=products, headers=headers)

def update_store_sync_db(store_id: str, source: str, config: dict):
    """Updates the sync source and config for a store in Supabase."""
    from agent.supabase_db import get_supabase_url, get_headers
    url = f"{get_supabase_url()}/rest/v1/stores?id=eq.{store_id}"
    payload = {"sync_source": source, "sync_config": config}
    requests.patch(url, json=payload, headers=get_headers())

# --- ROUTES ---

@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request):
    """Renders the main admin dashboard."""
    from agent.supabase_db import get_supabase_url, get_headers
    stores_res = requests.get(f"{get_supabase_url()}/rest/v1/stores?select=*", headers=get_headers())
    stores = stores_res.json() if stores_res.status_code == 200 else []
    return templates.TemplateResponse("admin.html", {"request": request, "stores": stores})

@app.post("/admin/sync/excel/{store_id}")
async def sync_excel(store_id: str, request: Request):
    """Handles Excel file upload and synchronization."""
    data = await request.json()
    products = data.get("products", [])
    if not products:
        return {"status": "error", "message": "لا توجد بيانات في الملف"}
    
    try:
        update_store_sync_db(store_id, "local", {})
        delete_store_products(store_id)
        for p in products: p["store_id"] = store_id
        upload_products_bulk(products, store_id)
        return {"status": "success", "message": f"تم استيراد {len(products)} منتج بنجاح!"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/admin/sync/gsheet/{store_id}")
async def sync_gsheet(store_id: str, payload: dict):
    """Enables and performs initial sync for Google Sheets."""
    url = payload.get("url", "")
    if not url: return {"status": "error", "message": "رابط الجدول مطلوب"}
    try:
        update_store_sync_db(store_id, "gsheet", {"url": url})
        success, msg, count = await perform_single_store_sync(store_id)
        if success:
            return {"status": "success", "message": f"تم ربط Google Sheets بنجاح! تم سحب {count} منتج."}
        else:
            return {"status": "error", "message": f"فشل المزامنة: {msg}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/admin/sync/supabase/{store_id}")
async def sync_external_supabase(store_id: str, payload: dict):
    """Enables and performs initial sync for external Supabase."""
    config = payload.get("config", {})
    if not config.get("url"): return {"status": "error", "message": "بيانات الاتصال ناقصة"}
    try:
        update_store_sync_db(store_id, "supabase", config)
        success, msg, count = await perform_single_store_sync(store_id)
        if success:
            return {"status": "success", "message": f"تم ربط Supabase بنجاح! تم سحب {count} منتج."}
        else:
            return {"status": "error", "message": f"فشل المزامنة: {msg}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/admin/sync/mysql/{store_id}")
async def sync_mysql(store_id: str, payload: dict):
    """Enables and performs initial sync for remote MySQL."""
    config = payload.get("config", {})
    if not config.get("host"): return {"status": "error", "message": "بيانات الاتصال ناقصة"}
    try:
        update_store_sync_db(store_id, "mysql", config)
        success, msg, count = await perform_single_store_sync(store_id)
        if success:
            return {"status": "success", "message": f"تم ربط MySQL بنجاح! تم سحب {count} منتج."}
        else:
            return {"status": "error", "message": f"فشل المزامنة: {msg}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/admin/api/sync/push/{store_id}")
async def receive_pushed_data(store_id: str, payload: dict):
    """Simple endpoint to receive pushed data from ai-sales.php."""
    products = payload.get("products", [])
    if not products: return {"status": "error"}
    try:
        delete_store_products(store_id)
        for p in products: p["store_id"] = store_id
        upload_products_bulk(products, store_id)
        return {"status": "success"}
    except: return {"status": "error"}

@app.post("/admin/sync/bridge/{store_id}")
async def sync_bridge(store_id: str, payload: dict):
    """Enables and performs initial sync via API Bridge."""
    url = payload.get("bridge_url", "")
    if not url: return {"status": "error", "message": "رابط الجسر مطلوب"}
    try:
        update_store_sync_db(store_id, "bridge", {"bridge_url": url})
        success, msg, count = await perform_single_store_sync(store_id)
        if success:
            return {"status": "success", "message": f"تم تفعيل الجسر بنجاح! تم سحب {count} من البيانات."}
        else:
            return {"status": "error", "message": f"فشل الجسر: {msg}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# --- BACKGROUND SYNC LOGIC ---

async def perform_single_store_sync(store_id: str):
    """Fetches remote data and replaces local data. Returns (success, msg, count)."""
    from agent.supabase_db import get_supabase_url, get_headers, search_live_gsheet, search_live_external_supabase, fetch_live_mysql, fetch_live_bridge
    import requests
    
    # 1. Get Store Config
    res = requests.get(f"{get_supabase_url()}/rest/v1/stores?id=eq.{store_id}&select=*", headers=get_headers())
    if res.status_code != 200 or not res.json(): 
        return False, "لم يتم العثور على إعدادات المتجر", 0
    
    store = res.json()[0]
    source = store.get("sync_source")
    config = store.get("sync_config")
    
    products = []
    error_msg = ""
    try:
        if source == "gsheet":
            products = search_live_gsheet([], config.get("url"))
            if not products: error_msg = "لم يتم العور على بيانات في الرابط أو الرابط غير صالح"
        elif source == "supabase":
            products = search_live_external_supabase([], config)
            if not products: error_msg = "فشل الاتصال بسوبر بيس الخارجي أو الجدول فارغ"
        elif source == "mysql":
            products, mysql_err = fetch_live_mysql(config)
            if mysql_err: error_msg = mysql_err
            elif not products: error_msg = "لا توجد بيانات في جدول MySQL المختار"
        elif source == "bridge":
            products, bridge_err = fetch_live_bridge(config.get("bridge_url"))
            if bridge_err: error_msg = bridge_err
            elif not products: error_msg = "الجسر لم يرجع أي بيانات"
    except Exception as e:
        error_msg = str(e)
    
    if products:
        delete_store_products(store_id)
        for p in products: p["store_id"] = store_id
        upload_products_bulk(products, store_id)
        return True, "Success", len(products)
    else:
        return False, error_msg or "لا توجد بيانات لسحبها", 0

async def background_sync_scheduler():
    """Loops every 5 minutes to sync all remote stores."""
    from agent.supabase_db import get_supabase_url, get_headers
    import requests
    
    while True:
        try:
            # Get all stores that are NOT local
            url = f"{get_supabase_url()}/rest/v1/stores?sync_source=neq.local&select=id"
            res = requests.get(url, headers=get_headers())
            if res.status_code == 200:
                stores = res.json()
                for s in stores:
                    await perform_single_store_sync(s["id"])
        except Exception as e:
            print(f"[!] Sync Scheduler Error: {e}")
        
        await asyncio.sleep(300) # 5 Minutes

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(background_sync_scheduler())

@app.get("/admin/download/bridge")
async def download_bridge_file(store_id: str, host: str = "", user: str = "", password: str = "", db: str = "", table: str = "products"):
    """Generates and serves a configured ai-sales.php on the fly."""
    php_template = f"""<?php
/**
 * AI Sales Agent - Easy Sync
 * Just upload this file and visit it or index.html to sync.
 */
$db_host = "{host}"; 
$db_user = "{user}";
$db_pass = "{password}";
$db_name = "{db}";
$table_name = "{table}";
$store_id = "{store_id}";
$platform_url = "https://ai-sales-agent-dreu.onrender.com/admin/api/sync/push/$store_id";

$conn = new mysqli($db_host, $db_user, $db_pass, $db_name);
if (!$conn->connect_error) {{
    $conn->set_charset("utf8mb4");
    $result = $conn->query("SELECT * FROM $table_name LIMIT 1000");
    $products = [];
    while($row = $result->fetch_assoc()) {{
        $keys = array_keys($row);
        $name_key = $keys[0];
        foreach($keys as $k) {{ if(stripos($k, 'name') !== false || stripos($k, 'اسم') !== false) {{ $name_key = $k; break; }} }}
        $details = $row; unset($details[$name_key]);
        $products[] = ["name" => $row[$name_key], "details" => $details];
    }}
    $conn->close();

    $ch = curl_init($platform_url);
    curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode(["products" => $products]));
    curl_setopt($ch, CURLOPT_HTTPHEADER, array('Content-Type:application/json'));
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_exec($ch);
    curl_close($ch);
}}
header("Content-Type: image/png");
echo base64_decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=");
?>"""
    return Response(
        content=php_template,
        media_type="application/x-httpd-php",
        headers={"Content-Disposition": "attachment; filename=ai-sales.php"}
    )

@app.get("/")
async def root_redirect():
    return RedirectResponse(url="/admin")

@app.post("/webhook")
async def evolution_webhook(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()
    background_tasks.add_task(handle_incoming_message, data)
    return {"status": "received"}

# --- SECURE PROXY ENDPOINTS FOR AUTHORIZED NUMBERS ---
@app.get("/admin/api/products")
async def get_store_products_api(store_id: str):
    """Fetches all products for a specific store to display in the admin UI."""
    from agent.supabase_db import get_supabase_url, get_headers
    import requests
    url = f"{get_supabase_url()}/rest/v1/products?store_id=eq.{store_id}&select=*"
    try:
        res = requests.get(url, headers=get_headers())
        return res.json()
    except Exception as e:
        return []
