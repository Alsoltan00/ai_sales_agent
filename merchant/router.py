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
    """صفحة إعدادات المتجر"""
    settings = get_store_settings(user["id"])
    return templates.TemplateResponse("merchant/store_settings.html", {"request": request, "user": user, "settings": settings})

@router.post("/api/store")
async def api_update_store(payload: StoreSettingsRequest, user: dict = Depends(verify_merchant)):
    """تحديث بيانات المتجر"""
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
    """صفحة التخطيط"""
    planning = get_planning_config(user["id"])
    return templates.TemplateResponse("merchant/planning.html", {"request": request, "user": user, "planning": planning})

@router.post("/api/planning")
async def api_update_planning(payload: PlanningRequest, user: dict = Depends(verify_merchant)):
    """تحديث إعدادات التخطيط"""
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



# --- Business Rules ---

@router.get("/business-rules", response_class=HTMLResponse)
async def business_rules_page(request: Request, user: dict = Depends(verify_merchant)):
    """صفحة قواعد العمل (Business Rules)"""
    supabase = get_supabase_client()
    rules = {}
    try:
        res = supabase.table("business_rules").select("rules_data").eq("client_id", user["id"]).single().execute()
        if res.data:
            rules = res.data.get("rules_data", {})
    except:
        pass
    return templates.TemplateResponse("merchant/business_rules.html", {"request": request, "user": user, "rules": rules})

@router.post("/api/business-rules")
async def api_update_business_rules(payload: dict, user: dict = Depends(verify_merchant)):
    """تحديث قواعد العمل"""
    supabase = get_supabase_client()
    try:
        # التحقق من وجود سجل سابق
        existing = supabase.table("business_rules").select("id").eq("client_id", user["id"]).execute()
        
        if existing.data:
            supabase.table("business_rules").update({
                "rules_data": payload,
                "updated_at": datetime.now().isoformat()
            }).eq("client_id", user["id"]).execute()
        else:
            supabase.table("business_rules").insert({
                "client_id": user["id"],
                "rules_data": payload,
                "updated_at": datetime.now().isoformat()
            }).execute()
            
        return {"status": "success", "message": "تم تحديث قواعد العمل بنجاح"}
    except Exception as e:
        return {"status": "error", "message": f"حدث خطأ: {str(e)}"}



# --- Data Sync ---

class SyncConfigRequest(BaseModel):
    source_type: str
    connection_details: dict
    table_name: str = ""
    sheet_name: str = ""

@router.get("/data-sync", response_class=HTMLResponse)
async def data_sync_page(request: Request, user: dict = Depends(verify_merchant)):
    """صفحة مزامنة البيانات"""
    sync_config = get_sync_config(user["id"])
    return templates.TemplateResponse("merchant/data_sync.html", {"request": request, "user": user, "sync_config": sync_config})

@router.post("/api/data-sync")
async def api_update_data_sync(payload: SyncConfigRequest, user: dict = Depends(verify_merchant)):
    """تحديث إعدادات المزامنة"""
    success = update_sync_config(user["id"], payload.model_dump())
    if success:
        return {"status": "success", "message": "تم تحديث إعدادات الربط بنجاح"}
    return {"status": "error", "message": "حدث خطأ أثناء الربط"}

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
    """صفحة الاستقبال والإرسال"""
    channels_config = get_channels_config(user["id"])
    return templates.TemplateResponse("merchant/channels.html", {"request": request, "user": user, "channels_config": channels_config})

@router.post("/api/channels")
async def api_update_channels(payload: ChannelsConfigRequest, user: dict = Depends(verify_merchant)):
    """تحديث إعدادات القنوات"""
    success = update_channels_config(user["id"], payload.model_dump())
    if success:
        return {"status": "success", "message": "تم حفظ إعدادات القنوات بنجاح"}
    return {"status": "error", "message": "حدث خطأ أثناء الحفظ"}

@router.post("/api/channels/test-whatsapp")
async def api_test_whatsapp(user: dict = Depends(verify_merchant)):
    """اختبار إرسال رسالة واتساب تجريبية"""
    from merchant.reception.whatsapp_evolution_receiver import _send_evolution_message
    from merchant.channels_config import get_channels_config
    from merchant.authorized_numbers import get_authorized_numbers

    # 1. جلب الإعدادات
    cfg = get_channels_config(user["id"])
    if not cfg or not cfg.get("evolution_api_url"):
        return {"status": "error", "message": "يرجى حفظ إعدادات Evolution API أولاً"}

    # 2. جلب أول رقم مصرح للإرسال له
    numbers = get_authorized_numbers(user["id"])
    if not numbers:
        return {"status": "error", "message": "يرجى إضافة رقم واحد على الأقل في قائمة الأرقام المصرّحة ليتم إرسال التجربة له"}
    
    test_phone = numbers[0]["phone_number"]
    test_msg = "🚀 تجربة ناجحة! السيرفر الخاص بك متصل الآن بـ Evolution API بشكل صحيح."

    # 3. محاولة الإرسال
    success = await _send_evolution_message(
        cfg["evolution_api_url"],
        cfg["evolution_api_key"],
        cfg["evolution_instance_name"],
        test_phone,
        test_msg
    )

    if success:
        return {"status": "success", "message": f"تم إرسال رسالة تجريبية بنجاح للرقم {test_phone}"}
    else:
        return {"status": "error", "message": "فشل الإرسال. تأكد من صحة الرابط، الـ API Key، واسم الجلسة."}

# --- Authorized Numbers ---

class AuthorizedNumberRequest(BaseModel):
    phone_number: str
    label: str = ""

class AllowAllRequest(BaseModel):
    allow_all: bool

@router.get("/authorized-numbers", response_class=HTMLResponse)
async def authorized_numbers_page(request: Request, user: dict = Depends(verify_merchant)):
    """صفحة الأرقام المصرّحة"""
    from merchant.authorized_numbers import get_authorized_numbers, get_allow_all_status, get_ignore_groups_status
    numbers = get_authorized_numbers(user["id"])
    allow_all = get_allow_all_status(user["id"])
    ignore_groups = get_ignore_groups_status(user["id"])
    return templates.TemplateResponse("merchant/authorized_numbers.html", {
        "request": request, 
        "user": user, 
        "numbers": numbers,
        "allow_all": allow_all,
        "ignore_groups": ignore_groups
    })

@router.post("/api/authorized-numbers")
async def api_add_authorized_number(payload: AuthorizedNumberRequest, user: dict = Depends(verify_merchant)):
    """إضافة رقم جديد"""
    success = add_authorized_number(user["id"], payload.phone_number, payload.label)
    if success:
        return {"status": "success", "message": "تم إضافة الرقم بنجاح"}
    return {"status": "error", "message": "حدث خطأ أثناء الإضافة"}

@router.delete("/api/authorized-numbers/{record_id}")
async def api_delete_authorized_number(record_id: str, user: dict = Depends(verify_merchant)):
    """حذف رقم"""
    success = delete_authorized_number(user["id"], record_id)
    if success:
        return {"status": "success", "message": "تم حذف الرقم بنجاح"}
    return {"status": "error", "message": "حدث خطأ أثناء الحذف"}

@router.post("/api/authorized-numbers/settings")
async def api_update_authorized_settings(payload: dict, user: dict = Depends(verify_merchant)):
    """تحديث إعدادات الأرقام والمجموعات"""
    from merchant.authorized_numbers import set_allow_all, set_ignore_groups
    
    if "allow_all" in payload:
        set_allow_all(user["id"], payload["allow_all"])
    
    if "ignore_groups" in payload:
        set_ignore_groups(user["id"], payload["ignore_groups"])
        
    return {"status": "success", "message": "تم تحديث الإعدادات بنجاح"}

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
