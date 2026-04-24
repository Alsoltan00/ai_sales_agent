import os
import csv
import io
import uvicorn
from fastapi import FastAPI, Request, File, UploadFile, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables FIRST before importing any agent modules
load_dotenv()

from agent.conversation_manager import handle_incoming_message
from agent.supabase_db import upload_products_bulk, delete_store_products, update_store_sync_db
import dotenv
import asyncio

app = FastAPI(title="Evolution AI Sales Agent")
templates = Jinja2Templates(directory="templates")

class SettingsUpdate(BaseModel):
    GROQ_API_KEY: str | None = None
    EVOLUTION_API_URL: str | None = None
    EVOLUTION_API_KEY: str | None = None
    EVOLUTION_INSTANCE_NAME: str | None = None
    SUPABASE_URL: str | None = None
    SUPABASE_KEY: str | None = None

@app.get("/")
async def root():
    """
    Root endpoint for health checks and easy access.
    """
    return RedirectResponse(url="/admin")

@app.get("/admin", response_class=HTMLResponse)
async def get_admin_panel(request: Request):
    """
    Renders the professional admin control panel with store selection.
    """
    from agent.supabase_db import get_supabase_url, get_headers
    import requests
    
    stores = []
    try:
        url = f"{get_supabase_url()}/rest/v1/stores?select=*"
        res = requests.get(url, headers=get_headers())
        if res.status_code == 200:
            stores = res.json()
    except:
        pass

    return templates.TemplateResponse("admin.html", {
        "request": request,
        "stores": stores,
        "groq_key": os.environ.get("GROQ_API_KEY", ""),
        "evolution_url": os.environ.get("EVOLUTION_API_URL", ""),
        "evolution_key": os.environ.get("EVOLUTION_API_KEY", ""),
        "supabase_url": os.environ.get("SUPABASE_URL", ""),
        "supabase_key": os.environ.get("SUPABASE_KEY", "")
    })

@app.post("/admin/settings")
async def update_settings(settings: SettingsUpdate):
    """
    Dynamically update the system environment variables and write them to .env
    """
    env_path = ".env"
    if not os.path.exists(env_path):
        open(env_path, 'a').close() # Create if missing

    # Update valid fields
    for key, value in settings.model_dump(exclude_none=True).items():
        if value and value.strip() != "":
            dotenv.set_key(env_path, key, value.strip())
            os.environ[key] = value.strip()
            
    return {"status": "success", "message": "Settings updated dynamically"}

@app.post("/admin/upload/{store_id}")
async def upload_file(store_id: str, file: UploadFile = File(...)):
    """
    Receives an Excel or CSV file, parses dynamic custom columns using Pandas,
    and bulk inserts them into Supabase.
    """
    import pandas as pd
    
    if not (file.filename.endswith('.csv') or file.filename.endswith('.xlsx') or file.filename.endswith('.xls')):
        return {"status": "error", "message": "يجب أن يكون الملف بصيغة Excel أو CSV!"}
        
    try:
        contents = await file.read()
        
        # Parse using Pandas based on extension
        if file.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents))
        else:
            df = pd.read_excel(io.BytesIO(contents))
            
        import json
        # Pandas to_json safely handles NaN/NaT and nested structures natively for APIs
        json_str = df.to_json(orient="records", force_ascii=False)
        raw_products_list = json.loads(json_str)
        
        # SMART SCHEMA-LESS MAPPING:
        # We take the first column as the 'name' and everything else goes into 'details'
        products_list = []
        cols = df.columns.tolist()
        
        # Try to find a 'name' column, otherwise use the first one
        name_col = next((c for c in cols if 'اسم' in str(c) or 'name' in str(c).lower()), cols[0])
        
        for _, row in df.iterrows():
            # Convert row to dict and handle NaN values
            row_dict = row.to_dict()
            clean_name = str(row_dict.get(name_col, "")).strip()
            
            if clean_name and clean_name != "nan":
                # Create the details object from all other columns
                details = {str(k): v for k, v in row_dict.items() if k != name_col and pd.notna(v)}
                
                products_list.append({
                    "name": clean_name,
                    "details": details,
                    "store_id": store_id
                })
        
        if not products_list:
            return {"status": "error", "message": "لم يتم العثور على بيانات صالحة في الملف."}
            
        # 1. Clear existing data for this store (Overwrite Policy)
        delete_store_products(store_id)
        
        # 2. Reset sync source to 'local' since this is a manual upload
        update_store_sync_db(store_id, "local", {})

        # 3. Bulk upload to Supabase
        success, msg = upload_products_bulk(products_list, store_id)
        
        if success:
            return {"status": "تم رفع البيانات بذكاء وتلقائية!", "count": len(products_list)}
        else:
            return {"status": "error", "message": msg}
    except Exception as e:
        return {"status": "error", "message": f"حدث خطأ أثناء معالجة الملف: {str(e)}"}

@app.post("/admin/sync/gsheet/{store_id}")
async def sync_gsheet(store_id: str, payload: dict):
    """
    Sets store to Google Sheet, CLEARS local data, and syncs immediately.
    """
    url = payload.get("url", "")
    if not url: return {"status": "error", "message": "الرابط مطلوب"}
    
    try:
        # 1. Clear old data immediately
        delete_store_products(store_id)
        # 2. Set new sync source
        update_store_sync_db(store_id, "gsheet", {"url": url})
        # 3. Pull data immediately (don't wait for scheduler)
        await perform_single_store_sync(store_id)
        return {"status": "success", "message": "تم مسح البيانات القديمة ومزامنة جوجل شيت بنجاح!"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/admin/sync/supabase/{store_id}")
async def sync_external_supabase(store_id: str, payload: dict):
    """
    Sets store to External Supabase, CLEARS local data, and syncs immediately.
    """
    try:
        delete_store_products(store_id)
        update_store_sync_db(store_id, "supabase", payload)
        await perform_single_store_sync(store_id)
        return {"status": "success", "message": "تم مسح البيانات القديمة وربط سوبر بيس الخارجي بنجاح!"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/admin/sync/mysql/{store_id}")
async def sync_mysql(store_id: str, payload: dict):
    """
    Sets store to External MySQL, CLEARS local data, and syncs immediately.
    """
    try:
        # 1. Clear old data immediately
        delete_store_products(store_id)
        # 2. Set new sync source
        update_store_sync_db(store_id, "mysql", payload)
        # 3. Pull data immediately
        await perform_single_store_sync(store_id)
        return {"status": "success", "message": "تم مسح البيانات القديمة وربط قاعدة MySQL بنجاح!"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# --- BACKGROUND SYNC LOGIC ---

async def perform_single_store_sync(store_id: str):
    """Fetches remote data and replaces local data for one store."""
    from agent.supabase_db import get_supabase_url, get_headers, search_live_gsheet, search_live_external_supabase, fetch_live_mysql
    import requests
    
    # 1. Get Store Config
    res = requests.get(f"{get_supabase_url()}/rest/v1/stores?id=eq.{store_id}&select=*", headers=get_headers())
    if res.status_code != 200 or not res.json(): return
    store = res.json()[0]
    
    source = store.get("sync_source")
    config = store.get("sync_config")
    
    products = []
    if source == "gsheet":
        products = search_live_gsheet([], config.get("url")) 
    elif source == "supabase":
        products = search_live_external_supabase([], config)
    elif source == "mysql":
        products = fetch_live_mysql(config)
    
    if products:
        delete_store_products(store_id)
        # Add store_id to each product before bulk upload
        for p in products: p["store_id"] = store_id
        upload_products_bulk(products, store_id)
        print(f"[+] Synced {len(products)} items for store {store_id} from {source}")

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
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/admin/api/numbers")
async def get_authorized_numbers_api(store_id: str = None):
    from agent.supabase_db import get_all_authorized_numbers
    try:
        data = get_all_authorized_numbers(store_id)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/admin/api/numbers")
async def add_authorized_number_api(payload: dict):
    from agent.supabase_db import add_authorized_number_db
    raw_phone = payload.get("phone", "")
    store_id = payload.get("store_id")
    # Sanitize: Keep only digits
    phone = "".join(filter(str.isdigit, str(raw_phone)))
    
    if not phone: raise HTTPException(status_code=400, detail="Invalid phone number format")
    try:
        add_authorized_number_db(phone, store_id)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/admin/api/stores")
async def create_store_api(store_data: dict):
    from agent.supabase_db import create_store_db
    try:
        create_store_db(store_data)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/admin/api/numbers/delete/{phone}")
async def delete_authorized_number_api(phone: str):
    from agent.supabase_db import delete_authorized_number_db
    try:
        delete_authorized_number_db(phone)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
