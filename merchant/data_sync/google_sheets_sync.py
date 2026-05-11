# merchant/data_sync/google_sheets_sync.py
# مزامنة بيانات العميل من Google Sheets
import pandas as pd
import io
import httpx
import json
from datetime import datetime
from database.db_client import get_db_client

async def sync_sheet(client_id: str, sheet_url: str, sheet_name: str = None):
    """يسحب بيانات الورقة ويحفظها في قاعدة بيانات العميل"""
    try:
        # تحويل رابط الورقة إلى رابط تصدير CSV
        if "/d/" not in sheet_url:
            return {"status": "error", "message": "رابط Google Sheet غير صالح"}
        
        parts = sheet_url.split("/d/")
        spreadsheet_id = parts[1].split("/")[0]
        
        # رابط التصدير (يفترض أن الورقة عامة: Anyone with the link can view)
        export_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv"
        # إذا كان هناك اسم ورقة محدد، يمكن إضافته (يتطلب معرفة الـ gid عادةً، لكن pandas/sheets تدعم التحويل أحياناً)
        # للمساعدة، سنحاول جلب الورقة الافتراضية
            
        async with httpx.AsyncClient() as client:
            response = await client.get(export_url, follow_redirects=True)
            if response.status_code != 200:
                return {"status": "error", "message": "فشل الوصول للورقة. تأكد أنها عامة (Anyone with the link can view)"}
            
            content = response.content
            df = pd.read_csv(io.BytesIO(content))
            
            # تنظيف البيانات
            df = df.dropna(how='all', axis=0).dropna(how='all', axis=1)
            data_json = df.to_json(orient="records", force_ascii=False)
            
            db = get_db_client()
            
            # حفظ في merchant_manual_data
            try:
                db.table("merchant_manual_data").delete().eq("client_id", client_id).execute()
            except:
                pass
                
            db.table("merchant_manual_data").insert({
                "client_id": client_id,
                "data": json.loads(data_json),
                "filename": f"Google Sheet",
                "updated_at": datetime.now().isoformat()
            }).execute()
            
            # تحديث وقت آخر مزامنة في sync_config
            try:
                db.table("sync_config").update({"last_synced_at": datetime.now().isoformat()}).eq("client_id", client_id).execute()
            except:
                pass
                
            return {"status": "success", "message": f"تمت مزامنة {len(df)} سجل من Google Sheets بنجاح."}
            
    except Exception as e:
        print(f"Google Sheets Sync error: {e}")
        return {"status": "error", "message": f"خطأ أثناء المزامنة: {str(e)}"}

def start_auto_sync(client_id: str, interval_minutes: int = 30):
    """placeholder for background task"""
    pass
