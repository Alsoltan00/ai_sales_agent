import asyncio
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from auth.session_manager import get_current_user
from database.db_client import get_supabase_client
from merchant.ai_training.ai_config import get_ai_config, update_ai_config, get_all_ai_configs, activate_ai_model
from merchant.planning.planning_config import get_planning_config, update_planning_config

router = APIRouter(prefix="/admin", tags=["Admin Dashboard"])
templates = Jinja2Templates(directory="templates")

def verify_admin(request: Request):
    user = get_current_user(request)
    if not user or user.get("user_type") != "admin_user":
        raise HTTPException(status_code=403, detail="غير مصرح لك بالدخول إلى هذه الصفحة")
    return user

def sanitize_data(data):
    """وظيفة لتنظيف البيانات وجعلها قابلة للتحويل إلى JSON"""
    if isinstance(data, list):
        return [sanitize_data(item) for item in data]
    if isinstance(data, dict):
        return {k: sanitize_data(v) for k, v in data.items()}
    if data is None: return None
    if isinstance(data, (str, int, float, bool)): return data
    return str(data)

@router.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request, user: dict = Depends(verify_admin)):
    """لوحة تحكم الإدارة الرئيسية"""
    def _fetch_stats():
        supabase = get_supabase_client()
        stats = {}
        try:
            res = supabase.table("clients").select("id", count="exact").eq("status", "active").execute()
            stats["active_clients"] = res.count
            res = supabase.table("new_client_requests").select("id", count="exact").eq("status", "pending").execute()
            stats["pending_requests"] = res.count
        except Exception as e:
            print(f"Error fetching stats: {e}")
        return stats
    stats = await asyncio.to_thread(_fetch_stats)
    return templates.TemplateResponse("admin.html", {"request": request, "user": user, "stats": stats})

# مسارات طلبات العملاء الجدد
@router.get("/api/requests/pending")
async def get_pending_requests(user: dict = Depends(verify_admin)):
    """جلب جميع طلبات الحسابات المعلقة"""
    perms = user.get("permissions") or {}
    if not perms.get("can_manage_new_clients") and not perms.get("is_admin"):
        raise HTTPException(status_code=403, detail="ليس لديك صلاحية لإدارة طلبات العملاء")
        
    def _fetch():
        supabase = get_supabase_client()
        return supabase.table("new_client_requests").select("*").eq("status", "pending").execute()
    res = await asyncio.to_thread(_fetch)
    return {"status": "success", "data": res.data}

@router.post("/api/requests/{request_id}/accept")
def accept_request(request_id: str, user: dict = Depends(verify_admin)):
    """الموافقة على طلب عميل وإنشاء حساب له"""
    perms = user.get("permissions") or {}
    if not perms.get("can_manage_new_clients") and not perms.get("is_admin"):
        raise HTTPException(status_code=403, detail="ليس لديك صلاحية")
        
    supabase = get_supabase_client()
    try:
        # جلب بيانات الطلب
        req_data = supabase.table("new_client_requests").select("*").eq("id", request_id).single().execute()
        
        if not req_data.data:
            return {"status": "error", "message": "الطلب غير موجود"}
            
        client_info = req_data.data
        
        # إذا كان الطلب يحتوي على هاش كلمة مرور، نستخدمه
        # وإلا ننشئ كلمة مرور افتراضية (رقم التواصل)
        final_pwd_hash = client_info.get("password_hash")
        if not final_pwd_hash:
            from passlib.context import CryptContext
            pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
            final_pwd_hash = pwd_context.hash(client_info["contact_number"])
        
        # حساب تاريخ انتهاء الاشتراك الافتراضي (30 يوم من الآن)
        from datetime import datetime, timedelta
        expiry_date = datetime.now() + timedelta(days=30)
        
        new_client = {
            "company_name": client_info["company_name"],
            "contact_number": client_info["contact_number"],
            "email": client_info.get("email"),
            "password_hash": final_pwd_hash,
            "store_url": client_info.get("store_link"),
            "status": "active",
            "subscription_plan": "basic",
            "subscription_ends_at": expiry_date.isoformat()
        }
        
        # إدراج العميل
        res_insert = supabase.table("clients").insert(new_client).execute()
        
        if not res_insert.data:
            return {"status": "error", "message": "فشل إنشاء حساب العميل"}
            
        new_client_id = res_insert.data[0].get("id")
        
        # تحديث حالة الطلب إلى accepted
        supabase.table("new_client_requests").update({
            "status": "accepted", 
            "reviewed_by": user.get("id")
        }).eq("id", request_id).execute()
        
        return {"status": "success", "message": "تم قبول العميل وإنشاء حسابه بنجاح", "client_id": str(new_client_id)}
    except Exception as e:
        print(f"Error accepting request: {e}")
        return {"status": "error", "message": f"حدث خطأ: {str(e)}"}

@router.get("/requests", response_class=HTMLResponse)
def admin_requests(request: Request, user: dict = Depends(verify_admin)):
    """صفحة طلبات العملاء الجدد (بانتظار الموافقة)"""
    return templates.TemplateResponse("admin_new_clients.html", {"request": request, "user": user})

@router.post("/api/requests/{request_id}/reject")
def reject_request(request_id: str, user: dict = Depends(verify_admin)):
    """رفض طلب العميل"""
    perms = user.get("permissions") or {}
    if not perms.get("can_manage_new_clients") and not perms.get("is_admin"):
        raise HTTPException(status_code=403, detail="ليس لديك صلاحية")
        
    supabase = get_supabase_client()
    try:
        supabase.table("new_client_requests").update({"status": "rejected", "reviewed_by": user["id"]}).eq("id", request_id).execute()
        return {"status": "success", "message": "تم رفض الطلب بنجاح"}
    except Exception as e:
        return {"status": "error", "message": "حدث خطأ أثناء الرفض"}

@router.get("/clients", response_class=HTMLResponse)
async def admin_clients(request: Request, user: dict = Depends(verify_admin)):
    """قائمة جميع العملاء النشطين"""
    perms = user.get("permissions") or {}
    if not perms.get("can_manage_clients") and not perms.get("is_admin"):
        raise HTTPException(status_code=403, detail="ليس لديك صلاحية لإدارة المتاجر والعملاء")
    def _fetch():
        supabase = get_supabase_client()
        res = supabase.table("clients").select("*").execute()
        return sanitize_data(res.data or [])
    safe_clients = await asyncio.to_thread(_fetch)
    return templates.TemplateResponse("admin_clients.html", {"request": request, "user": user, "clients": safe_clients})

@router.get("/subscriptions", response_class=HTMLResponse)
async def admin_subscriptions(request: Request, user: dict = Depends(verify_admin)):
    """إدارة اشتراكات العملاء والخطط مع تنظيف كامل للبيانات"""
    perms = user.get("permissions") or {}
    if not perms.get("can_manage_subscriptions") and not perms.get("is_admin"):
        raise HTTPException(status_code=403, detail="ليس لديك صلاحية لإدارة الاشتراكات والباقات")
    def _fetch_all():
        import json
        supabase = get_supabase_client()
        safe_clients = []
        safe_plans = []
        global_models = []
        try:
            res_clients = supabase.table("clients").select("*").execute()
            res_plans = supabase.table("subscription_plans").select("*").execute()
            res_models = supabase.table("global_ai_models").select("*").execute()
            safe_clients = sanitize_data(res_clients.data or [])
            global_models = sanitize_data(res_models.data or [])
            for plan in (res_plans.data or []):
                p = dict(plan)
                if p.get("permissions") and isinstance(p["permissions"], str):
                    try: p["permissions"] = json.loads(p["permissions"])
                    except: p["permissions"] = {}
                # تحويل assigned_model_ids من نص إلى قائمة
                if p.get("assigned_model_ids") and isinstance(p["assigned_model_ids"], str):
                    try: p["assigned_model_ids"] = json.loads(p["assigned_model_ids"])
                    except: p["assigned_model_ids"] = []
                if not p.get("assigned_model_ids"):
                    p["assigned_model_ids"] = []
                safe_plans.append(sanitize_data(p))
        except Exception as e:
            print(f"Error in admin_subscriptions: {e}")
        return safe_clients, safe_plans, global_models
    safe_clients, safe_plans, global_models = await asyncio.to_thread(_fetch_all)
    return templates.TemplateResponse("admin_subscriptions.html", {
        "request": request, 
        "user": user, 
        "clients": safe_clients,
        "plans": safe_plans,
        "global_models": global_models
    })

@router.post("/api/plans")
def api_create_plan(payload: dict, user: dict = Depends(verify_admin)):
    """إنشاء خطة اشتراك جديدة"""
    if not user.get("permissions", {}).get("can_manage_subscriptions") and not user.get("permissions", {}).get("is_admin"):
        raise HTTPException(status_code=403, detail="ليس لديك صلاحية")
        
    supabase = get_supabase_client()
    try:
        supabase.table("subscription_plans").insert(payload).execute()
        return {"status": "success", "message": "تم إنشاء الخطة بنجاح"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.put("/api/plans/{plan_id}")
def api_update_plan(plan_id: str, payload: dict, user: dict = Depends(verify_admin)):
    """تحديث خطة اشتراك موجودة"""
    if not user.get("permissions", {}).get("can_manage_subscriptions") and not user.get("permissions", {}).get("is_admin"):
        raise HTTPException(status_code=403, detail="ليس لديك صلاحية")
        
    supabase = get_supabase_client()
    try:
        supabase.table("subscription_plans").update(payload).eq("id", plan_id).execute()
        return {"status": "success", "message": "تم تحديث الخطة بنجاح"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.delete("/api/plans/{plan_id}")
def api_delete_plan(plan_id: str, user: dict = Depends(verify_admin)):
    """حذف خطة اشتراك"""
    if not user.get("permissions", {}).get("can_manage_subscriptions") and not user.get("permissions", {}).get("is_admin"):
        raise HTTPException(status_code=403, detail="ليس لديك صلاحية")
        
    supabase = get_supabase_client()
    try:
        supabase.table("subscription_plans").delete().eq("id", plan_id).execute()
        return {"status": "success", "message": "تم حذف الخطة بنجاح"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.post("/api/subscriptions/{client_id}/renew")
def renew_subscription(client_id: str, payload: dict, user: dict = Depends(verify_admin)):
    """تجديد اشتراك عميل"""
    if not user.get("permissions", {}).get("can_manage_subscriptions") and not user.get("permissions", {}).get("is_admin"):
        raise HTTPException(status_code=403, detail="ليس لديك صلاحية")
        
    days = int(payload.get("days", 30))
    plan_name = payload.get("plan", "pro")
    
    supabase = get_supabase_client()
    try:
        # جلب البيانات الحالية
        client_res = supabase.table("clients").select("subscription_ends_at").eq("id", client_id).single().execute()
        current_end = None
        if client_res.data and client_res.data.get("subscription_ends_at"):
            from datetime import datetime
            try:
                if isinstance(client_res.data["subscription_ends_at"], str):
                    current_end = datetime.fromisoformat(client_res.data["subscription_ends_at"].replace('Z', '+00:00'))
                else:
                    current_end = client_res.data["subscription_ends_at"]
            except:
                current_end = datetime.now()
        else:
            from datetime import datetime
            current_end = datetime.now()

        # حساب التاريخ الجديد
        from datetime import datetime, timedelta
        if current_end < datetime.now():
            new_end = datetime.now() + timedelta(days=days)
        else:
            new_end = current_end + timedelta(days=days)
            
        supabase.table("clients").update({
            "subscription_plan": plan_name,
            "subscription_ends_at": new_end.isoformat(),
            "status": "active"
        }).eq("id", client_id).execute()
        
        return {"status": "success", "message": f"تم تجديد الاشتراك لمدة {days} يوم بنجاح"}
    except Exception as e:
        return {"status": "error", "message": f"حدث خطأ: {str(e)}"}

@router.get("/users", response_class=HTMLResponse)
def admin_users(request: Request, user: dict = Depends(verify_admin)):
    """إدارة موظفي النظام (الأدمن)"""
    perms = user.get("permissions") or {}
    if not perms.get("can_manage_users") and not perms.get("is_admin"):
        raise HTTPException(status_code=403, detail="ليس لديك صلاحية لإدارة المستخدمين")
    supabase = get_supabase_client()
    res = supabase.table("sales_admin_users").select("*").execute()
    safe_users = sanitize_data(res.data or [])
    
    # تحديث بيانات المستخدم الحالي في الجلسة لضمان مزامنة الاسم والصلاحيات فوراً
    current_db_user = next((u for u in safe_users if str(u.get('id')) == str(user.get('id'))), None)
    if current_db_user:
        user['name'] = current_db_user.get('name')
        user['permissions'] = current_db_user.get('permissions')
        request.session['user'] = user

    return templates.TemplateResponse("admin_users.html", {"request": request, "user": user, "admin_users": safe_users})

@router.post("/api/users")
def api_create_user(payload: dict, user: dict = Depends(verify_admin)):
    """إنشاء مستخدم إداري جديد"""
    perms = user.get("permissions") or {}
    if not perms.get("can_manage_users") and not perms.get("is_admin"):
        raise HTTPException(status_code=403, detail="ليس لديك صلاحية")
        
    supabase = get_supabase_client()
    
    # Check if email exists
    existing = supabase.table("sales_admin_users").select("id").eq("email", payload.get("email")).execute()
    if existing.data:
        return {"status": "error", "message": "البريد الإلكتروني مسجل مسبقاً"}
        
    try:
        from passlib.context import CryptContext
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        
        raw_pwd = payload.get("password", "")
        # Bcrypt له حد أقصى 72 بايت
        safe_pwd = raw_pwd.encode('utf-8')[:72].decode('utf-8', 'ignore')
        
        new_user = {
            "name": payload.get("name"),
            "email": payload.get("email"),
            "password_hash": pwd_context.hash(safe_pwd),
            "permissions": payload.get("permissions", {})
        }
        
        supabase.table("sales_admin_users").insert(new_user).execute()
        return {"status": "success", "message": "تم إضافة المستخدم بنجاح"}
    except Exception as e:
        print(f"Error creating user: {e}")
        return {"status": "error", "message": f"فشل الإضافة: {str(e)}"}

@router.put("/api/users/{user_id}")
def api_update_user(user_id: str, payload: dict, request: Request, current_user: dict = Depends(verify_admin)):
    """تحديث بيانات/صلاحيات مستخدم إداري"""
    perms = current_user.get("permissions") or {}
    if not perms.get("can_manage_users") and not perms.get("is_admin"):
        raise HTTPException(status_code=403, detail="ليس لديك صلاحية")
        
    supabase = get_supabase_client()
    update_data = {
        "name": payload.get("name"),
        "permissions": payload.get("permissions", {})
    }
    
    try:
        raw_password = payload.get("password")
        if raw_password:
            from passlib.context import CryptContext
            pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
            # Bcrypt له حد أقصى 72 بايت وليس حرفاً، نقوم بالقص بدقة
            safe_password = raw_password.encode('utf-8')[:72].decode('utf-8', 'ignore')
            update_data["password_hash"] = pwd_context.hash(safe_password)
            
        supabase.table("sales_admin_users").update(update_data).eq("id", user_id).execute()
        
        # إذا كان المستخدم يعدل بيانات نفسه، نحدث الجلسة لكي يظهر الاسم الجديد فوراً
        if str(user_id) == str(current_user.get("id")):
            user_session = request.session.get("user", {})
            user_session["name"] = update_data["name"]
            user_session["permissions"] = update_data["permissions"]
            request.session["user"] = user_session
            
        return {"status": "success", "message": "تم تحديث بيانات المستخدم بنجاح"}
    except Exception as e:
        print(f"Error updating user: {e}")
        return {"status": "error", "message": f"فشل التحديث: {str(e)}"}

@router.delete("/api/users/{user_id}")
def api_delete_user(user_id: str, current_user: dict = Depends(verify_admin)):
    """حذف مستخدم إداري"""
    perms = current_user.get("permissions") or {}
    if not perms.get("can_manage_users") and not perms.get("is_admin"):
        raise HTTPException(status_code=403, detail="ليس لديك صلاحية")
        
    if current_user.get("id") == user_id:
        return {"status": "error", "message": "لا يمكنك حذف حسابك الحالي"}
        
    supabase = get_supabase_client()
    try:
        supabase.table("sales_admin_users").delete().eq("id", user_id).execute()
        return {"status": "success", "message": "تم حذف المستخدم بنجاح"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/api/clients/{client_id}/onboarding-settings")
async def get_client_onboarding_settings(client_id: str, user: dict = Depends(verify_admin)):
    """جلب إعدادات نوع النشاط ومسار الطلب للعميل"""
    config = await get_planning_config(client_id)
    return {"status": "success", "data": {
        "sales_type": config.get("sales_type"),
        "order_flow": config.get("order_flow"),
        "delivery_type": config.get("delivery_type")
    }}

@router.put("/api/clients/{client_id}/onboarding-settings")
def update_client_onboarding_settings(client_id: str, payload: dict, user: dict = Depends(verify_admin)):
    """تحديث إعدادات نوع النشاط ومسار الطلب للعميل"""
    sales_type = payload.get("sales_type")
    order_flow = payload.get("order_flow")
    delivery_type = payload.get("delivery_type")
    
    # تحديث بيانات التخطيط
    success = update_planning_config(client_id, {
        "sales_type": sales_type,
        "order_flow": order_flow,
        "delivery_type": delivery_type
    })
    
    # فحص ذكي: إذا كان أي حقل فارغاً، نعتبر الإعداد غير مكتمل
    # هذا يجبر التاجر على إكمال النواقص عند دخوله المرة القادمة
    onboarding_completed = True
    if not sales_type or not order_flow or not delivery_type:
        onboarding_completed = False
        
    from merchant.store_management.store_settings import update_store_settings
    update_store_settings(client_id, {"onboarding_completed": onboarding_completed})
        
    if success:
        return {"status": "success", "message": "تم تحديث إعدادات العميل بنجاح"}
    return {"status": "error", "message": "حدث خطأ أثناء التحديث"}

@router.post("/api/clients/{client_id}/reset-password")
def reset_client_password(client_id: str, payload: dict, user: dict = Depends(verify_admin)):
    """إعادة تعيين كلمة مرور العميل"""
    new_password = payload.get("new_password")
    if not new_password or len(new_password) < 8:
        return {"status": "error", "message": "كلمة المرور يجب أن تكون 8 أحرف على الأقل"}
        
    supabase = get_supabase_client()
    try:
        from passlib.context import CryptContext
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        
        # Bcrypt has a limit of 72 bytes
        safe_password = new_password.encode('utf-8')[:72].decode('utf-8', 'ignore')
        hashed = pwd_context.hash(safe_password)
        
        supabase.table("clients").update({"password_hash": hashed}).eq("id", client_id).execute()
        return {"status": "success", "message": "تم إعادة تعيين كلمة المرور بنجاح"}
    except Exception as e:
        return {"status": "error", "message": f"حدث خطأ: {str(e)}"}

@router.get("/models-pool", response_class=HTMLResponse)
def admin_models_pool(request: Request, user: dict = Depends(verify_admin)):
    """واجهة إدارة مكتبة النماذج العالمية مع تنظيف البيانات"""
    perms = user.get("permissions") or {}
    if not perms.get("can_manage_models") and not perms.get("is_admin"):
        raise HTTPException(status_code=403, detail="ليس لديك صلاحية لإدارة النماذج")
        
    supabase = get_supabase_client()
    # جلب النماذج من الجدول العالمي الجديد
    res = supabase.table("global_ai_models").select("*").execute()
    
    safe_models = sanitize_data(res.data or [])
    return templates.TemplateResponse("admin/models_pool.html", {"request": request, "user": user, "models": safe_models})

@router.post("/api/models-pool")
def admin_api_add_global_model(payload: dict, user: dict = Depends(verify_admin)):
    """إضافة نموذج جديد للمكتبة العالمية"""
    perms = user.get("permissions") or {}
    if not perms.get("can_manage_models") and not perms.get("is_admin"):
        raise HTTPException(status_code=403, detail="ليس لديك صلاحية")
        
    supabase = get_supabase_client()
    try:
        clean_payload = {
            "model_name": payload.get("model_name", "").strip(),
            "provider": payload.get("provider", "").strip().lower(),
            "model_id": payload.get("model_id", "").strip(),
            "api_key": payload.get("api_key", "").strip(),
            "base_url": payload.get("base_url", "").strip(),
            "capabilities": payload.get("capabilities", {})
        }
        supabase.table("global_ai_models").insert(clean_payload).execute()
        return {"status": "success", "message": "تم إضافة النموذج للمكتبة بنجاح"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.post("/api/models-pool/test")
async def admin_api_test_global_model(payload: dict, user: dict = Depends(verify_admin)):
    """تجربة النموذج والتأكد من صلاحيته قبل الحفظ"""
    perms = user.get("permissions") or {}
    if not perms.get("can_manage_models") and not perms.get("is_admin"):
        raise HTTPException(status_code=403, detail="ليس لديك صلاحية")

    provider = payload.get("provider", "").lower()
    api_key = payload.get("api_key", "").strip()
    model_id = payload.get("model_id", "").strip()
    base_url = payload.get("base_url", "").strip()

    if not all([provider, api_key, model_id]):
        return {"status": "error", "message": "جميع الحقول مطلوبة"}

    results = {
        "text": False, 
        "vision_in": False, "vision_out": False, 
        "audio_in": False, "audio_out": False
    }
    messages_with_image = [
        {"role": "user", "content": [
            {"type": "text", "text": "What is in this image?"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="}}
        ]}
    ]
    
    try:
        import httpx
        timeout = httpx.Timeout(20.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            # 1. اختبار النص (Text Test) - أساسي
            # 1. OpenAI Test
            if provider == "openai":
                res = await client.post("https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"model": model_id, "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 5}
                )
                if res.status_code == 200: 
                    results["text"] = True
                    # Vision In
                    res_v = await client.post("https://api.openai.com/v1/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}"},
                        json={"model": model_id, "messages": messages_with_image, "max_tokens": 5}
                    )
                    if res_v.status_code == 200: results["vision_in"] = True
            
            # 2. Google Gemini Test
            elif provider == "google" or provider == "gemini":
                res = await client.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={api_key}",
                    json={"contents": [{"parts": [{"text": "Hi"}]}]}
                )
                if res.status_code == 200: 
                    results["text"] = True
                    results["vision_in"] = True 
                    results["audio_in"] = True
                    # Check Native Audio Out
                    res_a = await client.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={api_key}",
                        json={"contents": [{"parts": [{"text": "say hi"}]}], "generationConfig": {"response_mime_type": "audio/wav"}}
                    )
                    if res_a.status_code == 200: results["audio_out"] = True

            elif provider == "groq":
                res = await client.post("https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"model": model_id, "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 5}
                )
                if res.status_code == 200: results["text"] = True

            elif provider == "xai":
                res = await client.post("https://api.x.ai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"model": model_id, "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 5}
                )
                if res.status_code == 200: results["text"] = True

            elif provider == "anthropic":
                res = await client.post("https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
                    json={"model": model_id, "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 5}
                )
                if res.status_code == 200: results["text"] = True

            elif provider == "openrouter":
                res = await client.post("https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"model": model_id, "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 5}
                )
                if res.status_code == 200: results["text"] = True

            elif provider == "huggingface":
                res = await client.post("https://api-inference.huggingface.co/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"model": model_id, "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 5}
                )
                if res.status_code == 200: results["text"] = True

            elif provider == "cerebras":
                res = await client.post("https://api.cerebras.ai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"model": model_id, "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 5}
                )
                if res.status_code == 200: results["text"] = True

            elif provider == "nvidia":
                res = await client.post("https://integrate.api.nvidia.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"model": model_id, "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 5}
                )
                if res.status_code == 200: results["text"] = True

            elif provider == "agentrouter":
                res = await client.post("https://agentrouter.org/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"model": model_id, "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 5}
                )
                if res.status_code == 200: results["text"] = True

            elif provider == "custom":
                endpoint = base_url.rstrip("/")
                if not endpoint.endswith("/chat/completions"):
                    endpoint += "/chat/completions"
                res = await client.post(endpoint,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"model": model_id, "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 5}
                )
                if res.status_code == 200: results["text"] = True

            if results["text"]:
                return {"status": "success", "message": "تم اختبار النموذج بنجاح", "capabilities": results}
            else:
                err = res.text[:200] if 'res' in locals() else "Unknown Error"
                return {"status": "error", "message": f"فشل اختبار النص: {err}"}
    except Exception as e:
        return {"status": "error", "message": f"خطأ تقني أثناء التجربة: {str(e)}"}

@router.delete("/api/models-pool/{model_id}")
def admin_api_delete_global_model(model_id: str, user: dict = Depends(verify_admin)):
    """حذف نموذج من المكتبة"""
    perms = user.get("permissions") or {}
    if not perms.get("can_manage_models") and not perms.get("is_admin"):
        raise HTTPException(status_code=403, detail="ليس لديك صلاحية")
        
    supabase = get_supabase_client()
    try:
        supabase.table("global_ai_models").delete().eq("id", model_id).execute()
        return {"status": "success", "message": "تم حذف النموذج من المكتبة"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# --- إعدادات خادم واتساب (Evolution API) ---

@router.get("/settings", response_class=HTMLResponse)
def admin_settings(request: Request, user: dict = Depends(verify_admin)):
    """صفحة الإعدادات العامة"""
    supabase = get_supabase_client()
    evolution_settings = {}
    try:
        res = supabase.table("global_settings").select("*").eq("key", "evolution_api").single().execute()
        if res.data:
            evolution_settings = res.data.get("value", {})
    except:
        pass
    return templates.TemplateResponse("admin/settings.html", {
        "request": request, "user": user, "evolution_settings": evolution_settings
    })

@router.get("/api/settings/evolution")
def get_evolution_settings(user: dict = Depends(verify_admin)):
    """جلب إعدادات Evolution API"""
    supabase = get_supabase_client()
    try:
        res = supabase.table("global_settings").select("*").eq("key", "evolution_api").single().execute()
        if res.data:
            return {"status": "success", "data": res.data.get("value", {})}
    except:
        pass
    return {"status": "success", "data": {}}

@router.post("/api/settings/evolution")
def save_evolution_settings(payload: dict, user: dict = Depends(verify_admin)):
    """حفظ إعدادات Evolution API"""
    supabase = get_supabase_client()
    value = {
        "url": (payload.get("url") or "").strip().rstrip("/"),
        "api_key": (payload.get("api_key") or "").strip()
    }
    try:
        existing = supabase.table("global_settings").select("id").eq("key", "evolution_api").execute()
        if existing.data:
            supabase.table("global_settings").update({"value": value}).eq("key", "evolution_api").execute()
        else:
            supabase.table("global_settings").insert({"key": "evolution_api", "value": value}).execute()
        return {"status": "success", "message": "تم حفظ إعدادات خادم واتساب بنجاح"}
    except Exception as e:
        return {"status": "error", "message": f"خطأ: {e}"}

@router.post("/api/settings/evolution/test")
async def test_evolution_connection(payload: dict, user: dict = Depends(verify_admin)):
    """اختبار الاتصال بخادم Evolution API"""
    url = (payload.get("url") or "").strip().rstrip("/")
    api_key = (payload.get("api_key") or "").strip()
    if not url or not api_key:
        return {"status": "error", "message": "يرجى إدخال الرابط والمفتاح"}
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.get(
                f"{url}/instance/fetchInstances",
                headers={"apikey": api_key}
            )
            if res.status_code == 200:
                data = res.json()
                count = len(data) if isinstance(data, list) else 0
                return {"status": "success", "message": f"✅ الاتصال ناجح! عدد الجلسات النشطة: {count}"}
            else:
                return {"status": "error", "message": f"فشل الاتصال. رمز الحالة: {res.status_code}"}
    except Exception as e:
        return {"status": "error", "message": f"فشل الاتصال: {e}"}

