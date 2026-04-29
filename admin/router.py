from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from auth.session_manager import get_current_user
from database.db_client import get_supabase_client
from merchant.ai_training.ai_config import get_ai_config, update_ai_config, get_all_ai_configs, activate_ai_model

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
    supabase = get_supabase_client()
    
    # جلب إحصائيات سريعة
    stats = {}
    try:
        # عدد العملاء النشطين
        res = supabase.table("clients").select("id", count="exact").eq("status", "active").execute()
        stats["active_clients"] = res.count
        
        # عدد الطلبات الجديدة
        res = supabase.table("new_client_requests").select("id", count="exact").eq("status", "pending").execute()
        stats["pending_requests"] = res.count
        
    except Exception as e:
        print(f"Error fetching stats: {e}")
        
    return templates.TemplateResponse("admin.html", {"request": request, "user": user, "stats": stats})

# مسارات طلبات العملاء الجدد
@router.get("/api/requests/pending")
async def get_pending_requests(user: dict = Depends(verify_admin)):
    """جلب جميع طلبات الحسابات المعلقة"""
    perms = user.get("permissions") or {}
    if not perms.get("can_manage_new_clients") and not perms.get("is_admin"):
        raise HTTPException(status_code=403, detail="ليس لديك صلاحية لإدارة طلبات العملاء")
        
    supabase = get_supabase_client()
    res = supabase.table("new_client_requests").select("*").eq("status", "pending").execute()
    return {"status": "success", "data": res.data}

@router.post("/api/requests/{request_id}/accept")
async def accept_request(request_id: str, user: dict = Depends(verify_admin)):
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
async def admin_requests(request: Request, user: dict = Depends(verify_admin)):
    """صفحة طلبات العملاء الجدد (بانتظار الموافقة)"""
    return templates.TemplateResponse("admin_new_clients.html", {"request": request, "user": user})

@router.post("/api/requests/{request_id}/reject")
async def reject_request(request_id: str, user: dict = Depends(verify_admin)):
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
        
    supabase = get_supabase_client()
    res = supabase.table("clients").select("*").execute()
    safe_clients = sanitize_data(res.data or [])
    return templates.TemplateResponse("admin_clients.html", {"request": request, "user": user, "clients": safe_clients})

@router.get("/subscriptions", response_class=HTMLResponse)
async def admin_subscriptions(request: Request, user: dict = Depends(verify_admin)):
    """إدارة اشتراكات العملاء والخطط مع تنظيف كامل للبيانات"""
    perms = user.get("permissions") or {}
    if not perms.get("can_manage_subscriptions") and not perms.get("is_admin"):
        raise HTTPException(status_code=403, detail="ليس لديك صلاحية لإدارة الاشتراكات والباقات")
        
    supabase = get_supabase_client()
    
    safe_clients = []
    safe_plans = []
    global_models = []
    
    try:
        # جلب العملاء
        res_clients = supabase.table("clients").select("*").execute()
        raw_clients = res_clients.data or []
        
        # جلب الخطط
        res_plans = supabase.table("subscription_plans").select("*").execute()
        raw_plans = res_plans.data or []
        
        # جلب نماذج الذكاء العالمية
        res_models = supabase.table("global_ai_models").select("*").execute()
        global_models = res_models.data or []
        
        # تنظيف البيانات بشكل كامل
        safe_clients = sanitize_data(raw_clients)
        global_models = sanitize_data(global_models)
        
        # معالجة الصلاحيات في الخطط بشكل خاص
        for plan in raw_plans:
            p = dict(plan)
            import json
            if p.get("permissions") and isinstance(p["permissions"], str):
                try: p["permissions"] = json.loads(p["permissions"])
                except: p["permissions"] = {}
            safe_plans.append(sanitize_data(p))
            
    except Exception as e:
        print(f"Error in admin_subscriptions: {e}")
        
    return templates.TemplateResponse("admin_subscriptions.html", {
        "request": request, 
        "user": user, 
        "clients": safe_clients,
        "plans": safe_plans,
        "global_models": global_models
    })

@router.post("/api/plans")
async def api_create_plan(payload: dict, user: dict = Depends(verify_admin)):
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
async def api_update_plan(plan_id: str, payload: dict, user: dict = Depends(verify_admin)):
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
async def api_delete_plan(plan_id: str, user: dict = Depends(verify_admin)):
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
async def renew_subscription(client_id: str, payload: dict, user: dict = Depends(verify_admin)):
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
async def admin_users(request: Request, user: dict = Depends(verify_admin)):
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
async def api_create_user(payload: dict, user: dict = Depends(verify_admin)):
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
async def api_update_user(user_id: str, payload: dict, request: Request, current_user: dict = Depends(verify_admin)):
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
async def api_delete_user(user_id: str, current_user: dict = Depends(verify_admin)):
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


@router.get("/clients/{client_id}/ai", response_class=HTMLResponse)
async def admin_client_ai_config(client_id: str, request: Request, user: dict = Depends(verify_admin)):
    """إدارة إعدادات الذكاء الاصطناعي لعميل محدد من قبل الأدمن"""
    supabase = get_supabase_client()
    # جلب بيانات العميل للتأكد من وجوده
    client_res = supabase.table("clients").select("company_name").eq("id", client_id).single().execute()
    if not client_res.data:
        raise HTTPException(status_code=404, detail="العميل غير موجود")
    
    ai_config = get_ai_config(client_id)
    all_models = get_all_ai_configs(client_id)
    
    return templates.TemplateResponse("admin/client_ai_config.html", {
        "request": request,
        "user": user,
        "client_name": client_res.data["company_name"],
        "client_id": client_id,
        "ai_config": ai_config,
        "all_models": all_models
    })

@router.post("/api/clients/{client_id}/ai")
async def admin_api_update_ai(client_id: str, payload: dict, user: dict = Depends(verify_admin)):
    """تحديث إعدادات الذكاء لعميل من قبل الأدمن"""
    success = update_ai_config(client_id, payload)
    if success:
        return {"status": "success", "message": "تم حفظ الإعدادات للعميل بنجاح"}
    return {"status": "error", "message": "حدث خطأ أثناء الحفظ"}

@router.post("/api/clients/{client_id}/ai/activate/{model_id_pk}")
async def admin_api_activate_model(client_id: str, model_id_pk: str, user: dict = Depends(verify_admin)):
    """تفعيل نموذج لعميل من قبل الأدمن"""
    success = activate_ai_model(client_id, model_id_pk)
    if success:
        return {"status": "success", "message": "تم تفعيل النموذج للعميل بنجاح"}
    return {"status": "error", "message": "حدث خطأ أثناء التفعيل"}

@router.get("/models-pool", response_class=HTMLResponse)
async def admin_models_pool(request: Request, user: dict = Depends(verify_admin)):
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
async def admin_api_add_global_model(payload: dict, user: dict = Depends(verify_admin)):
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
            "api_key": payload.get("api_key", "").strip()
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

    if not all([provider, api_key, model_id]):
        return {"status": "error", "message": "جميع الحقول مطلوبة"}

    try:
        import httpx
        timeout = httpx.Timeout(15.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            if provider == "openai":
                res = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"model": model_id, "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 5}
                )
            elif provider == "groq":
                res = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"model": model_id, "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 5}
                )
                # إذا فشل الاختبار، نحاول جلب قائمة النماذج المتاحة
                if res.status_code != 200:
                    try:
                        models_res = await client.get(
                            "https://api.groq.com/openai/v1/models",
                            headers={"Authorization": f"Bearer {api_key}"}
                        )
                        if models_res.status_code == 200:
                            models_data = models_res.json()
                            available = [m["id"] for m in models_data.get("data", [])]
                            available_str = ", ".join(sorted(available)[:10])
                            return {"status": "error", "message": f"النموذج '{model_id}' غير متاح. النماذج المتاحة لحسابك هي: {available_str}"}
                    except:
                        pass
                    error_msg = res.text[:300] if res.text else str(res.status_code)
                    return {"status": "error", "message": f"فشل الاتصال ({res.status_code}): {error_msg}"}
                return {"status": "success", "message": "تم الاتصال بالنموذج بنجاح!"}
                
            elif provider == "anthropic":
                res = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
                    json={"model": model_id, "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 5}
                )
            elif provider == "gemini":
                res = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={api_key}",
                    json={"contents": [{"parts": [{"text": "Hi"}]}]}
                )
            else:
                return {"status": "error", "message": "مزود الخدمة غير مدعوم للتجربة"}

            if res.status_code == 200:
                return {"status": "success", "message": "تم الاتصال بالنموذج بنجاح!"}
            else:
                error_msg = res.text[:300] if res.text else str(res.status_code)
                return {"status": "error", "message": f"فشل الاتصال ({res.status_code}): {error_msg}"}
    except Exception as e:
        return {"status": "error", "message": f"خطأ تقني أثناء التجربة: {str(e)}"}

@router.delete("/api/models-pool/{model_id}")
async def admin_api_delete_global_model(model_id: str, user: dict = Depends(verify_admin)):
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
