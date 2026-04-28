from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from auth.session_manager import get_current_user
from database.db_client import get_supabase_client

router = APIRouter(prefix="/admin", tags=["Admin Dashboard"])
templates = Jinja2Templates(directory="templates")

def verify_admin(request: Request):
    user = get_current_user(request)
    if not user or user.get("user_type") != "admin_user":
        raise HTTPException(status_code=403, detail="غير مصرح لك بالدخول إلى هذه الصفحة")
    return user

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
    if not user.get("permissions", {}).get("can_manage_new_clients") and not user.get("permissions", {}).get("is_admin"):
        raise HTTPException(status_code=403, detail="ليس لديك صلاحية لإدارة طلبات العملاء")
        
    supabase = get_supabase_client()
    res = supabase.table("new_client_requests").select("*").eq("status", "pending").execute()
    return {"status": "success", "data": res.data}

@router.post("/api/requests/{request_id}/accept")
async def accept_request(request_id: str, user: dict = Depends(verify_admin)):
    """الموافقة على طلب عميل وإنشاء حساب له"""
    if not user.get("permissions", {}).get("can_manage_new_clients") and not user.get("permissions", {}).get("is_admin"):
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
    if not user.get("permissions", {}).get("can_manage_new_clients") and not user.get("permissions", {}).get("is_admin"):
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
    supabase = get_supabase_client()
    res = supabase.table("clients").select("*").execute()
    return templates.TemplateResponse("admin_clients.html", {"request": request, "user": user, "clients": res.data})

@router.get("/subscriptions", response_class=HTMLResponse)
async def admin_subscriptions(request: Request, user: dict = Depends(verify_admin)):
    """إدارة اشتراكات العملاء والخطط"""
    supabase = get_supabase_client()
    
    safe_clients = []
    safe_plans = []
    
    try:
        # جلب العملاء
        res_clients = supabase.table("clients").select("*").execute()
        for client in (res_clients.data or []):
            c = dict(client)
            c["id"] = str(c.get("id", ""))
            # تأمين التاريخ
            if c.get("subscription_ends_at"):
                try:
                    if not isinstance(c["subscription_ends_at"], str):
                        c["subscription_ends_at"] = c["subscription_ends_at"].isoformat()
                except:
                    c["subscription_ends_at"] = str(c["subscription_ends_at"])
            safe_clients.append(c)
            
        # جلب الخطط
        res_plans = supabase.table("subscription_plans").select("*").execute()
        for plan in (res_plans.data or []):
            p = dict(plan)
            p["id"] = str(p.get("id", ""))
            import json
            if p.get("permissions"):
                if isinstance(p["permissions"], str):
                    try: p["permissions"] = json.loads(p["permissions"])
                    except: p["permissions"] = {}
                elif not isinstance(p["permissions"], dict):
                    p["permissions"] = {}
            else:
                p["permissions"] = {}
            safe_plans.append(p)
            
    except Exception as e:
        print(f"Error in admin_subscriptions: {e}")
        
    return templates.TemplateResponse("admin_subscriptions.html", {
        "request": request, 
        "user": user, 
        "clients": safe_clients,
        "plans": safe_plans
    })

@router.post("/api/plans")
async def api_create_plan(payload: dict, user: dict = Depends(verify_admin)):
    """إنشاء خطة اشتراك جديدة"""
    supabase = get_supabase_client()
    try:
        supabase.table("subscription_plans").insert(payload).execute()
        return {"status": "success", "message": "تم إنشاء الخطة بنجاح"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.put("/api/plans/{plan_id}")
async def api_update_plan(plan_id: str, payload: dict, user: dict = Depends(verify_admin)):
    """تحديث خطة اشتراك موجودة"""
    supabase = get_supabase_client()
    try:
        supabase.table("subscription_plans").update(payload).eq("id", plan_id).execute()
        return {"status": "success", "message": "تم تحديث الخطة بنجاح"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.delete("/api/plans/{plan_id}")
async def api_delete_plan(plan_id: str, user: dict = Depends(verify_admin)):
    """حذف خطة اشتراك"""
    supabase = get_supabase_client()
    try:
        supabase.table("subscription_plans").delete().eq("id", plan_id).execute()
        return {"status": "success", "message": "تم حذف الخطة بنجاح"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.post("/api/subscriptions/{client_id}/renew")
async def renew_subscription(client_id: str, payload: dict, user: dict = Depends(verify_admin)):
    """تجديد اشتراك عميل"""
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
    supabase = get_supabase_client()
    res = supabase.table("sales_admin_users").select("*").execute()
    return templates.TemplateResponse("admin_users.html", {"request": request, "user": user, "admin_users": res.data})
