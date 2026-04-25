"""
=============================================================================
  AI Sales Platform - Main Application (FastAPI)
=============================================================================
  Multi-tenant architecture with per-store database isolation.
  All routes organized by feature domain.
=============================================================================
"""

import os
import json
import asyncio
import logging
from typing import List, Optional
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException, Header
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from agent.conversation_manager import handle_incoming_message
import requests
from agent.database import (
    initialize_database, migrate_old_data,
    create_store, fetch_stores, fetch_store_by_id, update_store, delete_store,
    update_store_sync_db, delete_store_products, upload_products_bulk,
    fetch_products_by_store, fetch_authorized_numbers, add_authorized_number,
    delete_authorized_number, get_store_columns, save_store_columns,
    search_live_gsheet, search_live_external_supabase, fetch_live_mysql, fetch_live_bridge
)

app = FastAPI(title="AI Sales Platform", version="2.0")
templates = Jinja2Templates(directory="templates")


# =============================================================================
#  STARTUP & INITIALIZATION
# =============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize DB schema and start background tasks."""
    try:
        initialize_database()
        migrate_old_data()
        print("[+] Database ready.")
    except Exception as e:
        print(f"[!] DB Init Warning: {e}")
    
    asyncio.create_task(background_sync_scheduler())


# =============================================================================
#  ADMIN DASHBOARD
# =============================================================================

@app.get("/", response_class=RedirectResponse)
async def root_redirect():
    return RedirectResponse(url="/admin")

@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request):
    """Renders the main admin dashboard."""
    try:
        stores = fetch_stores()
        return templates.TemplateResponse(
            request=request, name="admin.html", context={"stores": stores}
        )
    except Exception as e:
        return HTMLResponse(
            content=f"""<html><body style='font-family:sans-serif;padding:40px;'>
            <h1 style='color:#ef4444;'>⚠️ Database Connection Error</h1>
            <p style='font-size:1.2rem;'><b>{str(e)}</b></p>
            <hr><p>Check your environment variables: <code>DB_HOST</code>, <code>DB_PORT</code>, 
            <code>DB_USER</code>, <code>DB_PASS</code>, <code>DB_NAME</code></p>
            </body></html>""",
            status_code=500
        )


import os
import requests

EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "https://evolution-api-latest-qxsg.onrender.com")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "Aseel.709293")

# =============================================================================
#  STORE MANAGEMENT API
# =============================================================================

@app.post("/admin/api/stores")
async def api_add_store(payload: dict):
    """Creates a new store with its own isolated database schema."""
    try:
        # Combine advanced AI settings into a single JSON system_prompt
        ai_config = {
            "about": payload.get("about", ""),
            "tone": payload.get("tone", "احترافي ومحترم"),
            "policy": payload.get("policy", ""),
            "faq": payload.get("faq", "")
        }
        
        store_id = create_store(
            name=payload.get("name", "متجر جديد"),
            instance_name=payload.get("evolution_instance_name", ""),
            system_prompt=json.dumps(ai_config, ensure_ascii=False)
        )
        return {"status": "success", "store_id": store_id}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/admin/api/stores/{store_id}")
async def api_get_store(store_id: str):
    """Fetches a single store's details including parsed AI config."""
    store = fetch_store_by_id(store_id)
    if not store:
        return {"status": "error", "message": "Store not found"}
        
    # Parse the system_prompt back into a dict for the frontend
    ai_config = {"about": "", "tone": "", "policy": "", "faq": ""}
    try:
        if store.get("system_prompt"):
            parsed = json.loads(store["system_prompt"])
            if isinstance(parsed, dict):
                ai_config.update(parsed)
            else:
                ai_config["about"] = store["system_prompt"]
    except:
        ai_config["about"] = store.get("system_prompt", "")
        
    store["ai_config"] = ai_config
    return {"status": "success", "store": store}

@app.put("/admin/api/stores/{store_id}")
async def api_update_store(store_id: str, payload: dict):
    """Updates an existing store's configuration."""
    try:
        ai_config = {
            "about": payload.get("about", ""),
            "tone": payload.get("tone", "احترافي ومحترم"),
            "policy": payload.get("policy", ""),
            "faq": payload.get("faq", "")
        }
        update_store(
            store_id,
            name=payload.get("name"),
            instance_name=payload.get("evolution_instance_name"),
            system_prompt=json.dumps(ai_config, ensure_ascii=False)
        )
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.delete("/admin/api/stores/{store_id}")
async def api_delete_store(store_id: str):
    """Deletes a store and ALL its data (schema dropped entirely)."""
    try:
        # Also try to delete the WhatsApp instance from Evolution API if possible
        store = fetch_store_by_id(store_id)
        if store and store.get("evolution_instance_name"):
            headers = {"apikey": EVOLUTION_API_KEY}
            requests.delete(f"{EVOLUTION_API_URL}/instance/delete/{store['evolution_instance_name']}", headers=headers)
            
        delete_store(store_id)
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# =============================================================================
#  WHATSAPP INTEGRATION API (EVOLUTION)
# =============================================================================

@app.post("/admin/api/whatsapp/link")
async def link_whatsapp(payload: dict):
    """Creates an Evolution instance and returns the QR code base64."""
    instance_name = payload.get("instance_name")
    if not instance_name:
        return {"status": "error", "message": "اسم النسخة مطلوب"}
        
    headers = {
        "apikey": EVOLUTION_API_KEY,
        "Content-Type": "application/json"
    }
    
    # 1. Create Instance
    create_payload = {
        "instanceName": instance_name,
        "token": instance_name,
        "qrcode": True
    }
    
    try:
        # Force delete if exists to get a fresh QR
        requests.delete(f"{EVOLUTION_API_URL}/instance/delete/{instance_name}", headers=headers)
        
        res = requests.post(f"{EVOLUTION_API_URL}/instance/create", json=create_payload, headers=headers)
        if res.status_code not in [200, 201]:
            return {"status": "error", "message": f"فشل إنشاء النسخة: {res.text}"}
            
        data = res.json()
        qr_base64 = data.get("qrcode", {}).get("base64")
        
        # 2. Set Webhook
        webhook_payload = {
            "webhook": {
                "enabled": True,
                "url": "https://ai-sales-agent-dreu.onrender.com/webhook",
                "byEvents": False,
                "base64": False,
                "events": ["MESSAGES_UPSERT"]
            }
        }
        requests.post(f"{EVOLUTION_API_URL}/webhook/set/{instance_name}", json=webhook_payload, headers=headers)
        
        return {"status": "success", "qr": qr_base64}
        
    except Exception as e:
        return {"status": "error", "message": str(e)}


# =============================================================================
#  PRODUCTS API
# =============================================================================

@app.get("/admin/api/products")
async def api_get_products(store_id: str):
    """Fetches all products for a store from its isolated schema."""
    return fetch_products_by_store(store_id)

@app.get("/admin/api/columns")
async def api_get_columns(store_id: str):
    """Returns the column names for a store (auto-detected or manually set)."""
    return {"columns": get_store_columns(store_id)}

@app.put("/admin/api/columns")
async def api_update_columns(payload: dict):
    """Allows the merchant to rename/reorder columns."""
    store_id = payload.get("store_id")
    columns = payload.get("columns", [])
    if store_id and columns:
        save_store_columns(store_id, columns)
        return {"status": "success"}
    return {"status": "error", "message": "store_id and columns required"}


# =============================================================================
#  AUTHORIZED NUMBERS API
# =============================================================================

@app.get("/admin/api/numbers")
async def api_get_numbers(store_id: str):
    """Fetches authorized numbers for a store."""
    return fetch_authorized_numbers(store_id)

@app.post("/admin/api/numbers")
async def api_add_number(payload: dict):
    """Adds a number to a store's whitelist."""
    store_id = payload.get("store_id")
    phone = payload.get("phone", "").strip()
    if not phone or not store_id:
        raise HTTPException(status_code=400, detail="phone and store_id required")
    
    success = add_authorized_number(phone, store_id)
    if success:
        return {"status": "success"}
    return {"status": "error", "message": "فشل إضافة الرقم"}

@app.delete("/admin/api/numbers/{phone}")
async def api_delete_number(phone: str, store_id: str):
    """Removes a number from a store's whitelist."""
    success = delete_authorized_number(phone, store_id)
    if success:
        return {"status": "success"}
    return {"status": "error", "message": "فشل حذف الرقم"}


# =============================================================================
#  DATA SYNC ROUTES
# =============================================================================

from fastapi import FastAPI, Request, BackgroundTasks, HTTPException, Header, UploadFile, File
import pandas as pd
import io

@app.post("/admin/upload/{store_id}")
async def upload_file_direct(store_id: str, file: UploadFile = File(...)):
    """Handles direct Excel/CSV file upload and parses it."""
    try:
        content = await file.read()
        filename = file.filename.lower()
        
        if filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content))
        elif filename.endswith((".xls", ".xlsx")):
            df = pd.read_excel(io.BytesIO(content))
        else:
            return {"status": "error", "message": "صيغة الملف غير مدعومة. يرجى رفع ملف إكسيل أو CSV"}
            
        # Convert df to list of dicts, replacing NaN with None
        df = df.where(pd.notnull(df), None)
        products = df.to_dict(orient='records')
        
        if not products:
            return {"status": "error", "message": "لا توجد بيانات في الملف"}
            
        update_store_sync_db(store_id, "local", {})
        delete_store_products(store_id)
        upload_products_bulk(products, store_id)
        
        return {"status": "success", "message": f"تم استيراد {len(products)} منتج بنجاح!"}
    except Exception as e:
        return {"status": "error", "message": f"حدث خطأ أثناء معالجة الملف: {str(e)}"}

@app.post("/admin/sync/excel/{store_id}")
async def sync_excel(store_id: str, request: Request):
    """Handles JSON payload with products (legacy or API integration)."""
    data = await request.json()
    products = data.get("products", [])
    if not products:
        return {"status": "error", "message": "لا توجد بيانات في الملف"}
    
    try:
        update_store_sync_db(store_id, "local", {})
        delete_store_products(store_id)
        upload_products_bulk(products, store_id)
        return {"status": "success", "message": f"تم استيراد {len(products)} منتج بنجاح!"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/admin/sync/gsheet/{store_id}")
async def sync_gsheet(store_id: str, payload: dict):
    """Enables Google Sheets sync for a store."""
    url = payload.get("url", "")
    if not url:
        return {"status": "error", "message": "رابط الجدول مطلوب"}
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
    """Enables external Supabase sync for a store."""
    config = payload.get("config", {})
    if not config.get("url"):
        return {"status": "error", "message": "بيانات الاتصال ناقصة"}
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
    """Enables MySQL sync for a store."""
    config = payload.get("config", {})
    if not config.get("host"):
        return {"status": "error", "message": "بيانات الاتصال ناقصة"}
    try:
        update_store_sync_db(store_id, "mysql", config)
        success, msg, count = await perform_single_store_sync(store_id)
        if success:
            return {"status": "success", "message": f"تم ربط MySQL بنجاح! تم سحب {count} منتج."}
        else:
            return {"status": "error", "message": f"فشل المزامنة: {msg}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/admin/sync/bridge/{store_id}")
async def sync_bridge(store_id: str, payload: dict):
    """Enables API Bridge sync for a store."""
    url = payload.get("bridge_url", "")
    if not url:
        return {"status": "error", "message": "رابط الجسر مطلوب"}
    try:
        update_store_sync_db(store_id, "bridge", {"bridge_url": url})
        success, msg, count = await perform_single_store_sync(store_id)
        if success:
            return {"status": "success", "message": f"تم تفعيل الجسر بنجاح! تم سحب {count} من البيانات."}
        else:
            return {"status": "error", "message": f"فشل الجسر: {msg}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/admin/api/sync/push/{store_id}")
async def receive_pushed_data(store_id: str, payload: dict):
    """Receives pushed data from external bridges (ai-sales.php)."""
    products = payload.get("products", [])
    if not products:
        return {"status": "error"}
    try:
        delete_store_products(store_id)
        upload_products_bulk(products, store_id)
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# =============================================================================
#  BRIDGE FILE GENERATOR
# =============================================================================

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


# =============================================================================
#  WEBHOOK (WhatsApp via Evolution API)
# =============================================================================

@app.post("/webhook")
async def evolution_webhook(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()
    background_tasks.add_task(handle_incoming_message, data)
    return {"status": "received"}


# =============================================================================
#  BACKGROUND SYNC SCHEDULER
# =============================================================================

async def perform_single_store_sync(store_id: str):
    """Fetches remote data and replaces local data. Returns (success, msg, count)."""
    store = fetch_store_by_id(store_id)
    if not store: 
        return False, "لم يتم العثور على إعدادات المتجر", 0
    
    source = store.get("sync_source")
    config = store.get("sync_config") or {}
    
    products = []
    error_msg = ""
    try:
        if source == "gsheet":
            products = search_live_gsheet([], config.get("url"))
            if not products: error_msg = "لم يتم العثور على بيانات في الرابط أو الرابط غير صالح"
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
        upload_products_bulk(products, store_id)
        return True, "Success", len(products)
    else:
        return False, error_msg or "لا توجد بيانات لسحبها", 0

async def background_sync_scheduler():
    """Loops every 5 minutes to sync all remote stores."""
    while True:
        try:
            stores = fetch_stores()
            for s in stores:
                if s.get("sync_source", "local") != "local":
                    await perform_single_store_sync(s["id"])
        except Exception as e:
            print(f"[!] Sync Scheduler Error: {e}")
        
        await asyncio.sleep(300)  # 5 Minutes
