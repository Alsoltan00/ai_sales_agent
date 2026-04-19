import os
import csv
import io
import uvicorn
from fastapi import FastAPI, Request, File, UploadFile, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables FIRST before importing any agent modules
load_dotenv()

from agent.conversation_manager import handle_incoming_message
from agent.supabase_db import upload_products_bulk
import dotenv

app = FastAPI(title="Evolution AI Sales Agent")
templates = Jinja2Templates(directory="templates")

class SettingsUpdate(BaseModel):
    GROQ_API_KEY: str | None = None
    EVOLUTION_API_URL: str | None = None
    EVOLUTION_API_KEY: str | None = None
    EVOLUTION_INSTANCE_NAME: str | None = None
    SUPABASE_URL: str | None = None
    SUPABASE_KEY: str | None = None

@app.get("/admin", response_class=HTMLResponse)
async def get_admin_panel(request: Request):
    """
    Renders the professional N8N-style admin control panel.
    """
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "groq_key": os.environ.get("GROQ_API_KEY", ""),
        "evolution_url": os.environ.get("EVOLUTION_API_URL", ""),
        "evolution_key": os.environ.get("EVOLUTION_API_KEY", ""),
        "evolution_instance": os.environ.get("EVOLUTION_INSTANCE_NAME", ""),
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

@app.post("/admin/upload")
async def upload_file(file: UploadFile = File(...)):
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
        
        # AUTOMATIC EXCEL TO DATABASE MAPPING:
        # Maps the user's specific Arabic Excel headers to the NEW clean DB schema
        column_mapping = {
            "رقم الباركود": "barcode",
            "اسم الصنف": "name",
            "الوحدة": "unit",
            "العبوه": "package",
            "سعر البيع": "price",
            "الكمية المتوفرة": "stock"
        }
        
        products_list = []
        for row in raw_products_list:
            clean_row = {}
            # Ensure EVERY row has ALL the keys (PostgREST requires uniform keys for bulk insert)
            for arabic_key, db_key in column_mapping.items():
                val = row.get(arabic_key)
                if val is not None and str(val).strip() != "":
                    clean_row[db_key] = val
                else:
                    clean_row[db_key] = None # Fill missing with null
            
            # If the row has a valid product name, include it
            if clean_row.get("name"):
                products_list.append(clean_row)
        
        if not products_list:
            return {"status": "error", "message": "لم يتم العثور على أي منتجات صالحة. تأكد أن الإكسيل يحتوي على عمود 'اسم الصنف'."}
            
        # Send mapped rows directly to Supabase
        success = upload_products_bulk(products_list)
        
        if success:
            return {"status": "تم رفع المنتجات والأعمدة بنجاح!", "count": len(products_list)}
        else:
            return {"status": "حدث خطأ بالرفع. تأكد أن كل عناوين الأعمدة في ملف الإكسيل موجودة فعلياً كأعمدة في جدول products."}
    except Exception as e:
        return {"status": "خطأ برمجي", "message": str(e)}

@app.get("/")
def read_root():
    return {"status": "AI Sales Agent Server is running smoothly 🚀"}

@app.post("/webhook/evo-whatsapp")
async def receive_webhook(request: Request):
    """
    This endpoint receives messages from Evolution API.
    """
    payload = await request.json()
    
    # Run the core conversation handling logic asynchronously
    # (In production, consider adding to a background task queue if it takes long)
    try:
        await handle_incoming_message(payload)
        return {"status": "Message processed successfully"}
    except Exception as e:
        print(f"Error processing message: {e}")
        return {"status": "Error", "message": str(e)}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
