import os
import csv
import io
import uvicorn
from fastapi import FastAPI, Request, File, UploadFile, BackgroundTasks
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv

# Load environment variables FIRST before importing any agent modules
load_dotenv()

from agent.conversation_manager import handle_incoming_message
from agent.supabase_db import upload_products_bulk

app = FastAPI(title="Evolution AI Sales Agent")

@app.get("/admin", response_class=HTMLResponse)
def get_admin_panel():
    """
    A built-in simple admin interface to upload products via CSV.
    """
    html_content = """
    <html>
        <head>
            <title>إدارة منتجات الذكاء الاصطناعي</title>
            <style>
                body { font-family: Arial, sans-serif; background: #f4f7f6; direction: rtl; text-align: center; padding-top: 50px; }
                .box { background: white; width: 400px; margin: auto; padding: 30px; border-radius: 10px; box-shadow: 0px 4px 10px rgba(0,0,0,0.1); }
                h2 { color: #333; }
                input[type=file] { margin: 20px 0; }
                button { background: #4CAF50; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; }
                button:hover { background: #45a049; }
            </style>
        </head>
        <body>
            <div class="box">
                <h2>رفع المنتجات للسيرفر 🚀</h2>
                <p>قم برفع ملف المنتجات (Excel أو CSV) هنا ليتم إضافته إلى قاعدة بيانات Supabase فوراً.</p>
                <form action="/admin/upload" enctype="multipart/form-data" method="post">
                    <input name="file" type="file" required accept=".csv, application/vnd.openxmlformats-officedocument.spreadsheetml.sheet, application/vnd.ms-excel">
                    <br>
                    <button type="submit">رفع المنتجات</button>
                </form>
            </div>
        </body>
    </html>
    """
    return html_content

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
