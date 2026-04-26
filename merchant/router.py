from fastapi import APIRouter, Request, HTTPException, Depends, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import pandas as pd
import io
import json
from datetime import datetime
from pydantic import BaseModel
from auth.session_manager import get_current_user
from database.db_client import get_supabase_client

from merchant.store_management.store_settings import get_store_settings, update_store_settings
from merchant.planning.planning_config import get_planning_config, update_planning_config
from merchant.ai_training.ai_config import get_ai_config, update_ai_config
from merchant.data_sync.sync_config import get_sync_config, update_sync_config
from merchant.channels_config import get_channels_config, update_channels_config
from merchant.authorized_numbers import get_authorized_numbers, add_authorized_number, delete_authorized_number, set_allow_all, get_allow_all_status

router = APIRouter(prefix="/merchant", tags=["Merchant Home"])
templates = Jinja2Templates(directory="templates")

def verify_merchant(request: Request):
    user = get_current_user(request)
    if not user or user.get("user_type") != "merchant":
        raise HTTPException(status_code=403, detail="غير مصرح لك بالدخول إلى لوحة التاجر")
    return user

@router.get("/home", response_class=HTMLResponse)
async def merchant_home(request: Request, user: dict = Depends(verify_merchant)):
    """لوحة التاجر الرئيسية (Home)"""
    return templates.TemplateResponse("merchant_home.html", {"request": request, "user": user})

# --- Store Management ---

class StoreSettingsRequest(BaseModel):
    company_name: str
    contact_number: str
    email: str = None
    store_url: str = None

@router.get("/store", response_class=HTMLResponse)
async def store_settings_page(request: Request, user: dict = Depends(verify_merchant)):
    """طµظپط­ط© ط¥ط¹ط¯ط§ط¯ط§طھ ط§ظ„ظ…طھط¬ط±"""
    settings = get_store_settings(user["id"])
    return templates.TemplateResponse("merchant/store_settings.html", {"request": request, "user": user, "settings": settings})

@router.post("/api/store")
async def api_update_store(payload: StoreSettingsRequest, user: dict = Depends(verify_merchant)):
    """طھط­ط¯ظٹط« ط¨ظٹط§ظ†ط§طھ ط§ظ„ظ…طھط¬ط±"""
    success = update_store_settings(user["id"], payload.model_dump())
    if success:
        return {"status": "success", "message": "طھظ… طھط­ط¯ظٹط« ط§ظ„ط¥ط¹ط¯ط§ط¯ط§طھ ط¨ظ†ط¬ط§ط­"}
    return {"status": "error", "message": "ط­ط¯ط« ط®ط·ط£ ط£ط«ظ†ط§ط، ط§ظ„طھط­ط¯ظٹط«"}

# --- Planning ---

class PlanningRequest(BaseModel):
    ai_agent_name: str = None
    ai_tone: str = None
    business_description: str = None

@router.get("/planning", response_class=HTMLResponse)
async def planning_page(request: Request, user: dict = Depends(verify_merchant)):
    """طµظپط­ط© ط§ظ„طھط®ط·ظٹط·"""
    planning = get_planning_config(user["id"])
    return templates.TemplateResponse("merchant/planning.html", {"request": request, "user": user, "planning": planning})

@router.post("/api/planning")
async def api_update_planning(payload: PlanningRequest, user: dict = Depends(verify_merchant)):
    """طھط­ط¯ظٹط« ط¥ط¹ط¯ط§ط¯ط§طھ ط§ظ„طھط®ط·ظٹط·"""
    success = update_planning_config(user["id"], payload.model_dump())
    if success:
        return {"status": "success", "message": "طھظ… طھط­ط¯ظٹط« ط¨ظٹط§ظ†ط§طھ ط§ظ„طھط®ط·ظٹط· ط¨ظ†ط¬ط§ط­"}
    return {"status": "error", "message": "ط­ط¯ط« ط®ط·ط£ ط£ط«ظ†ط§ط، ط§ظ„طھط­ط¯ظٹط«"}

# --- AI Training ---

class AIConfigRequest(BaseModel):
    model_config = {'protected_namespaces': ()}
    model_name: str
    provider: str
    api_key: str
    model_id: str

@router.get("/ai-training", response_class=HTMLResponse)
async def ai_training_page(request: Request, user: dict = Depends(verify_merchant)):
    """طµظپط­ط© ط¥ط¹ط¯ط§ط¯ط§طھ ط§ظ„ط°ظƒط§ط، ط§ظ„ط§طµط·ظ†ط§ط¹ظٹ"""
    ai_config = get_ai_config(user["id"])
    return templates.TemplateResponse("merchant/ai_training.html", {"request": request, "user": user, "ai_config": ai_config})

@router.post("/api/ai-training")
async def api_update_ai_training(payload: AIConfigRequest, user: dict = Depends(verify_merchant)):
    """طھط­ط¯ظٹط« ط¥ط¹ط¯ط§ط¯ط§طھ ط§ظ„ظ†ظ…ظˆط°ط¬"""
    success = update_ai_config(user["id"], payload.model_dump())
    if success:
        return {"status": "success", "message": "طھظ… ط­ظپط¸ ط¥ط¹ط¯ط§ط¯ط§طھ ط§ظ„ظ†ظ…ظˆط°ط¬ ط¨ظ†ط¬ط§ط­"}
    return {"status": "error", "message": "ط­ط¯ط« ط®ط·ط£ ط£ط«ظ†ط§ط، ط§ظ„ط­ظپط¸"}

# --- Data Sync ---

class SyncConfigRequest(BaseModel):
    source_type: str
    connection_details: dict
    table_name: str = ""
    sheet_name: str = ""

@router.get("/data-sync", response_class=HTMLResponse)
async def data_sync_page(request: Request, user: dict = Depends(verify_merchant)):
    """طµظپط­ط© ظ…ط²ط§ظ…ظ†ط© ط§ظ„ط¨ظٹط§ظ†ط§طھ"""
    sync_config = get_sync_config(user["id"])
    return templates.TemplateResponse("merchant/data_sync.html", {"request": request, "user": user, "sync_config": sync_config})

@router.post("/api/data-sync")
async def api_update_data_sync(payload: SyncConfigRequest, user: dict = Depends(verify_merchant)):
    """طھط­ط¯ظٹط« ط¥ط¹ط¯ط§ط¯ط§طھ ط§ظ„ظ…ط²ط§ظ…ظ†ط©"""
    success = update_sync_config(user["id"], payload.model_dump())
    if success:
        return {"status": "success", "message": "طھظ… طھط­ط¯ظٹط« ط¥ط¹ط¯ط§ط¯ط§طھ ط§ظ„ط±ط¨ط· ط¨ظ†ط¬ط§ط­"}
    return {"status": "error", "message": "ط­ط¯ط« ط®ط·ط£ ط£ط«ظ†ط§ط، ط§ظ„ط±ط¨ط·"}

@router.post("/api/data-sync/upload")
async def api_upload_data_sync(file: UploadFile = File(...), user: dict = Depends(verify_merchant)):
    """رفع ومعالجة ملف Excel أو CSV يدوياً"""
    try:
        content = await file.read()
        filename = file.filename
        
        # قراءة الملف باستخدام pandas (الصف الأول هو العنوان تلقائياً)
        if filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(content))
        else:
            df = pd.read_excel(io.BytesIO(content))
            
        # تنظيف البيانات: حذف الصفوف والأعمدة الفارغة تماماً
        df = df.dropna(how='all', axis=0).dropna(how='all', axis=1)
        
        # تحويل البيانات إلى JSON
        data_json = df.to_json(orient="records", force_ascii=False)
        
        supabase = get_supabase_client()
        
        # 1. تحديث إعدادات المزامنة لتكون excel
        update_sync_config(user["id"], {
            "source_type": "excel",
            "connection_details": {"filename": filename}
        })
        
        # 2. حفظ البيانات في الجدول الجديد
        # ملاحظة: نستخدم upsert إذا كان العميل موجوداً بالفعل
        # في SQLAlchemy Mock: insert سيعالج الأمر إذا أضفنا منطق الـ upsert أو حذفنا القديم
        
        # حذف البيانات القديمة أولاً لضمان التحديث (بما أننا نستخدم mock client)
        try:
            supabase.table("merchant_manual_data").delete().eq("client_id", user["id"]).execute()
        except:
            pass
            
        supabase.table("merchant_manual_data").insert({
            "client_id": user["id"],
            "data": json.loads(data_json),
            "filename": filename,
            "updated_at": datetime.now().isoformat()
        }).execute()
        
        return {"status": "success", "message": f"تم رفع ومعالجة الملف '{filename}' بنجاح. تم استيراد {len(df)} سجل."}
        
    except Exception as e:
        print(f"Upload error: {str(e)}")
        return {"status": "error", "message": f"خطأ أثناء معالجة الملف: {str(e)}"}

# --- Channels Configuration (Reception & Sending) ---

class ChannelsConfigRequest(BaseModel):
    telegram_bot_token: str = None
    whatsapp_provider: str = "evolution"
    evolution_api_url: str = None
    evolution_api_key: str = None
    evolution_instance_name: str = None
    meta_phone_number_id: str = None
    meta_access_token: str = None
    meta_verify_token: str = None

@router.get("/channels", response_class=HTMLResponse)
async def channels_page(request: Request, user: dict = Depends(verify_merchant)):
    """طµظپط­ط© ط§ظ„ط§ط³طھظ‚ط¨ط§ظ„ ظˆط§ظ„ط¥ط±ط³ط§ظ„"""
    channels_config = get_channels_config(user["id"])
    return templates.TemplateResponse("merchant/channels.html", {"request": request, "user": user, "channels_config": channels_config})

@router.post("/api/channels")
async def api_update_channels(payload: ChannelsConfigRequest, user: dict = Depends(verify_merchant)):
    """طھط­ط¯ظٹط« ط¥ط¹ط¯ط§ط¯ط§طھ ط§ظ„ظ‚ظ†ظˆط§طھ"""
    success = update_channels_config(user["id"], payload.model_dump())
    if success:
        return {"status": "success", "message": "طھظ… ط­ظپط¸ ط¥ط¹ط¯ط§ط¯ط§طھ ط§ظ„ظ‚ظ†ظˆط§طھ ط¨ظ†ط¬ط§ط­"}
    return {"status": "error", "message": "ط­ط¯ط« ط®ط·ط£ ط£ط«ظ†ط§ط، ط§ظ„ط­ظپط¸"}

# --- Authorized Numbers ---

class AuthorizedNumberRequest(BaseModel):
    phone_number: str
    label: str = ""

class AllowAllRequest(BaseModel):
    allow_all: bool

@router.get("/authorized-numbers", response_class=HTMLResponse)
async def authorized_numbers_page(request: Request, user: dict = Depends(verify_merchant)):
    """طµظپط­ط© ط§ظ„ط£ط±ظ‚ط§ظ… ط§ظ„ظ…طµط±ظ‘ط­ط©"""
    numbers = get_authorized_numbers(user["id"])
    allow_all = get_allow_all_status(user["id"])
    return templates.TemplateResponse("merchant/authorized_numbers.html", {
        "request": request, 
        "user": user, 
        "numbers": numbers,
        "allow_all": allow_all
    })

@router.post("/api/authorized-numbers")
async def api_add_authorized_number(payload: AuthorizedNumberRequest, user: dict = Depends(verify_merchant)):
    """ط¥ط¶ط§ظپط© ط±ظ‚ظ… ط¬ط¯ظٹط¯"""
    success = add_authorized_number(user["id"], payload.phone_number, payload.label)
    if success:
        return {"status": "success", "message": "طھظ… ط¥ط¶ط§ظپط© ط§ظ„ط±ظ‚ظ… ط¨ظ†ط¬ط§ط­"}
    return {"status": "error", "message": "ط­ط¯ط« ط®ط·ط£ ط£ط«ظ†ط§ط، ط§ظ„ط¥ط¶ط§ظپط©"}

@router.delete("/api/authorized-numbers/{record_id}")
async def api_delete_authorized_number(record_id: str, user: dict = Depends(verify_merchant)):
    """ط­ط°ظپ ط±ظ‚ظ…"""
    success = delete_authorized_number(user["id"], record_id)
    if success:
        return {"status": "success", "message": "طھظ… ط­ط°ظپ ط§ظ„ط±ظ‚ظ… ط¨ظ†ط¬ط§ط­"}
    return {"status": "error", "message": "ط­ط¯ط« ط®ط·ط£ ط£ط«ظ†ط§ط، ط§ظ„ط­ط°ظپ"}

@router.post("/api/authorized-numbers/settings")
async def api_update_allow_all(payload: AllowAllRequest, user: dict = Depends(verify_merchant)):
    """طھط­ط¯ظٹط« ط®ظٹط§ط± ط§ظ„ط³ظ…ط§ط­ ظ„ظ„ط¬ظ…ظٹط¹"""
    success = set_allow_all(user["id"], payload.allow_all)
    if success:
        return {"status": "success", "message": "طھظ… طھط­ط¯ظٹط« ط§ظ„ط¥ط¹ط¯ط§ط¯ط§طھ ط¨ظ†ط¬ط§ط­"}
    return {"status": "error", "message": "ط­ط¯ط« ط®ط·ط£ ط£ط«ظ†ط§ط، ط§ظ„طھط­ط¯ظٹط«"}
