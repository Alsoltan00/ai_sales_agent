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
        return {"status": "success", "message": "تم تحديث الإعدادات بنجاح"}
    return {"status": "error", "message": "حدث خطأ أثناء التحديث"}

class PasswordChangeRequest(BaseModel):
    new_password: str

@router.post("/api/store/password")
async def api_change_password(payload: PasswordChangeRequest, user: dict = Depends(verify_merchant)):
    """تغيير كلمة مرور التاجر"""
    import hashlib
    if len(payload.new_password) < 6:
        return {"status": "error", "message": "كلمة المرور يجب أن تكون 6 أحرف على الأقل"}
    hashed = hashlib.sha256(payload.new_password.encode()).hexdigest()
    supabase = get_supabase_client()
    try:
        supabase.table("clients").update({"password_hash": hashed}).eq("id", user["id"]).execute()
        return {"status": "success", "message": "تم تحديث كلمة المرور بنجاح"}
    except Exception as e:
        return {"status": "error", "message": f"حدث خطأ: {str(e)}"}

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
        return {"status": "success", "message": "تم تحديث بيانات التخطيط بنجاح"}
    return {"status": "error", "message": "حدث خطأ أثناء التحديث"}

@router.get("/api/planning/columns")
async def api_get_columns(user: dict = Depends(verify_merchant)):
    """جلب أعمدة البيانات المزامنة مع إعدادات التدريب"""
    supabase = get_supabase_client()
    try:
        # جلب البيانات المخزنة
        data_res = supabase.table("merchant_manual_data").select("data").eq("client_id", user["id"]).single().execute()
        if not data_res.data or not data_res.data.get("data"):
            return {"columns": []}
        rows = data_res.data["data"]
        if not rows:
            return {"columns": []}
        col_names = list(rows[0].keys()) if rows else []

        # جلب إعدادات التدريب المحفوظة
        saved_res = supabase.table("column_training").select("*").eq("client_id", user["id"]).execute()
        saved_map = {r["column_name"]: r for r in (saved_res.data or [])}

        columns = [{
            "name": c,
            "note": saved_map.get(c, {}).get("note", ""),
            "is_disabled": saved_map.get(c, {}).get("is_disabled", False)
        } for c in col_names]
        return {"columns": columns}
    except Exception as e:
        return {"columns": []}

class ColumnTrainingItem(BaseModel):
    column_name: str
    note: str = ""
    is_disabled: bool = False

class ColumnTrainingRequest(BaseModel):
    columns: list[ColumnTrainingItem]

@router.post("/api/planning/columns")
async def api_save_columns(payload: ColumnTrainingRequest, user: dict = Depends(verify_merchant)):
    """حفظ إعدادات الأعمدة"""
    supabase = get_supabase_client()
    try:
        for col in payload.columns:
            # جرب تحديث أولاً، ثم إدراج إذا لم يوجد
            existing = supabase.table("column_training").select("id").eq("client_id", user["id"]).eq("column_name", col.column_name).execute()
            if existing.data:
                supabase.table("column_training").update({
                    "note": col.note,
                    "is_disabled": col.is_disabled
                }).eq("client_id", user["id"]).eq("column_name", col.column_name).execute()
            else:
                supabase.table("column_training").insert({
                    "client_id": user["id"],
                    "column_name": col.column_name,
                    "note": col.note,
                    "is_disabled": col.is_disabled
                }).execute()
        return {"status": "success", "message": "تم حفظ إعدادات الأعمدة بنجاح"}
    except Exception as e:
        return {"status": "error", "message": f"حدث خطأ: {str(e)}"}

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
        return {"status": "success", "message": "تم حفظ إعدادات النموذج بنجاح"}
    return {"status": "error", "message": "حدث خطأ أثناء الحفظ"}

class AITestRequest(BaseModel):
    model_config = {'protected_namespaces': ()}
    provider: str
    model_id: str
    api_key: str

@router.post("/api/ai-training/test")
async def api_test_ai_model(payload: AITestRequest, user: dict = Depends(verify_merchant)):
    """اختبار نموذج الذكاء الاصطناعي قبل الحفظ"""
    import httpx
    test_prompt = "قل مرحباً بجملة واحدة فقط."
    try:
        if payload.provider == "openai":
            url = "https://api.openai.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {payload.api_key}", "Content-Type": "application/json"}
            body = {"model": payload.model_id, "messages": [{"role": "user", "content": test_prompt}], "max_tokens": 50}
            async with httpx.AsyncClient(timeout=15) as client:
                res = await client.post(url, headers=headers, json=body)
            data = res.json()
            if "error" in data:
                return {"status": "error", "message": data["error"].get("message", "خطأ غير معروف")}
            reply = data["choices"][0]["message"]["content"]
            return {"status": "success", "response": reply}

        elif payload.provider == "anthropic":
            url = "https://api.anthropic.com/v1/messages"
            headers = {"x-api-key": payload.api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
            body = {"model": payload.model_id, "max_tokens": 50, "messages": [{"role": "user", "content": test_prompt}]}
            async with httpx.AsyncClient(timeout=15) as client:
                res = await client.post(url, headers=headers, json=body)
            data = res.json()
            if "error" in data:
                return {"status": "error", "message": data["error"].get("message", "خطأ")}
            reply = data["content"][0]["text"]
            return {"status": "success", "response": reply}

        elif payload.provider == "groq":
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {payload.api_key}", "Content-Type": "application/json"}
            body = {"model": payload.model_id, "messages": [{"role": "user", "content": test_prompt}], "max_tokens": 50}
            async with httpx.AsyncClient(timeout=15) as client:
                res = await client.post(url, headers=headers, json=body)
            data = res.json()
            if "error" in data:
                return {"status": "error", "message": str(data["error"])}
            reply = data["choices"][0]["message"]["content"]
            return {"status": "success", "response": reply}
        else:
            return {"status": "error", "message": "مزود الخدمة غير معروف"}
    except Exception as e:
        return {"status": "error", "message": f"فشل الاتصال بالنموذج: {str(e)}"}

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
    """تحديث خيار السماح للجميع"""
    success = set_allow_all(user["id"], payload.allow_all)
    if success:
        return {"status": "success", "message": "تم تحديث الإعدادات بنجاح"}
    return {"status": "error", "message": "حدث خطأ أثناء التحديث"}

# --- Data Display View ---

@router.get("/data-view", response_class=HTMLResponse)
async def data_view_page(request: Request, user: dict = Depends(verify_merchant)):
    """صفحة عرض البيانات المزامنة"""
    return templates.TemplateResponse("merchant/data_display.html", {"request": request, "user": user})

@router.get("/api/data-view")
async def api_get_data_view(user: dict = Depends(verify_merchant)):
    """جلب البيانات المزامنة للعرض"""
    supabase = get_supabase_client()
    try:
        # جلب البيانات اليدوية (Excel/CSV)
        data_res = supabase.table("merchant_manual_data").select("data, filename").eq("client_id", user["id"]).single().execute()
        if data_res.data and data_res.data.get("data"):
            rows = data_res.data["data"]
            return {"status": "ok", "data": rows, "source_type": "excel"}

        # جلب إعدادات المزامنة لمعرفة المصدر
        sync_res = supabase.table("sync_config").select("source_type").eq("client_id", user["id"]).single().execute()
        source = sync_res.data.get("source_type", "") if sync_res.data else ""
        return {"status": "no_data", "data": [], "source_type": source}
    except Exception as e:
        return {"status": "no_data", "data": [], "source_type": ""}
