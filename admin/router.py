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
    
    # ط¬ظ„ط¨ ط¥ط­طµط§ط¦ظٹط§طھ ط³ط±ظٹط¹ط©
    stats = {}
    try:
        # ط¹ط¯ط¯ ط§ظ„ط¹ظ…ظ„ط§ط، ط§ظ„ظ†ط´ط·ظٹظ†
        res = supabase.table("clients").select("id", count="exact").eq("status", "active").execute()
        stats["active_clients"] = res.count
        
        # ط¹ط¯ط¯ ط§ظ„ط·ظ„ط¨ط§طھ ط§ظ„ط¬ط¯ظٹط¯ط©
        res = supabase.table("new_client_requests").select("id", count="exact").eq("status", "pending").execute()
        stats["pending_requests"] = res.count
        
    except Exception as e:
        print(f"Error fetching stats: {e}")
        
    return templates.TemplateResponse("admin.html", {"request": request, "user": user, "stats": stats})

# ظ…ط³ط§ط±ط§طھ ط·ظ„ط¨ط§طھ ط§ظ„ط¹ظ…ظ„ط§ط، ط§ظ„ط¬ط¯ط¯
@router.get("/api/requests/pending")
async def get_pending_requests(user: dict = Depends(verify_admin)):
    """ط¬ظ„ط¨ ط¬ظ…ظٹط¹ ط·ظ„ط¨ط§طھ ط§ظ„ط­ط³ط§ط¨ط§طھ ط§ظ„ظ…ط¹ظ„ظ‚ط©"""
    if not user.get("permissions", {}).get("can_manage_new_clients") and not user.get("permissions", {}).get("is_admin"):
        raise HTTPException(status_code=403, detail="ظ„ظٹط³ ظ„ط¯ظٹظƒ طµظ„ط§ط­ظٹط© ظ„ط¥ط¯ط§ط±ط© ط·ظ„ط¨ط§طھ ط§ظ„ط¹ظ…ظ„ط§ط،")
        
    supabase = get_supabase_client()
    res = supabase.table("new_client_requests").select("*").eq("status", "pending").execute()
    return {"status": "success", "data": res.data}

@router.post("/api/requests/{request_id}/accept")
async def accept_request(request_id: str, user: dict = Depends(verify_admin)):
    """ط§ظ„ظ…ظˆط§ظپظ‚ط© ط¹ظ„ظ‰ ط·ظ„ط¨ ط¹ظ…ظٹظ„ ظˆط¥ظ†ط´ط§ط، ط­ط³ط§ط¨ ظ„ظ‡"""
    if not user.get("permissions", {}).get("can_manage_new_clients") and not user.get("permissions", {}).get("is_admin"):
        raise HTTPException(status_code=403, detail="ظ„ظٹط³ ظ„ط¯ظٹظƒ طµظ„ط§ط­ظٹط©")
        
    supabase = get_supabase_client()
    try:
        # ط¬ظ„ط¨ ط¨ظٹط§ظ†ط§طھ ط§ظ„ط·ظ„ط¨
        req_data = supabase.table("new_client_requests").select("*").eq("id", request_id).single().execute()
        
        if not req_data.data:
            return {"status": "error", "message": "ط§ظ„ط·ظ„ط¨ ط؛ظٹط± ظ…ظˆط¬ظˆط¯"}
            
        client_info = req_data.data
        
        # ط¥ظ†ط´ط§ط، ط­ط³ط§ط¨ ط§ظ„ط¹ظ…ظٹظ„ ظپظٹ ط¬ط¯ظˆظ„ clients
        # ط§ظپطھط±ط§ط¶ظٹط§ظ‹ ظƒظ„ظ…ط© ط§ظ„ظ…ط±ظˆط± ظ‡ظٹ ط±ظ‚ظ… ط§ظ„طھظˆط§طµظ„ (ظٹطھظ… طھط؛ظٹظٹط±ظ‡ط§ ظ„ط§ط­ظ‚ط§ظ‹ ظ…ظ† ظ‚ط¨ظ„ ط§ظ„ط¹ظ…ظٹظ„)
        from passlib.context import CryptContext
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        default_pwd = pwd_context.hash(client_info["contact_number"])
        
        new_client = {
            "company_name": client_info["company_name"],
            "contact_number": client_info["contact_number"],
            "password_hash": default_pwd,
            "status": "active"
        }
        
        # ط¥ط¯ط±ط§ط¬ ط§ظ„ط¹ظ…ظٹظ„
        res_insert = supabase.table("clients").insert(new_client).execute()
        new_client_id = res_insert.data[0]["id"]
        
        # طھط­ط¯ظٹط« ط­ط§ظ„ط© ط§ظ„ط·ظ„ط¨ ط¥ظ„ظ‰ accepted
        supabase.table("new_client_requests").update({"status": "accepted", "reviewed_by": user["id"]}).eq("id", request_id).execute()
        
        return {"status": "success", "message": "طھظ… ظ‚ط¨ظˆظ„ ط§ظ„ط¹ظ…ظٹظ„ ظˆط¥ظ†ط´ط§ط، ط­ط³ط§ط¨ظ‡ ط¨ظ†ط¬ط§ط­", "client_id": new_client_id}
    except Exception as e:
        print(f"Error accepting request: {e}")
        return {"status": "error", "message": "ط­ط¯ط« ط®ط·ط£ ط£ط«ظ†ط§ط، ظ…ط¹ط§ظ„ط¬ط© ط§ظ„ط·ظ„ط¨"}

@router.post("/api/requests/{request_id}/reject")
async def reject_request(request_id: str, user: dict = Depends(verify_admin)):
    """ط±ظپط¶ ط·ظ„ط¨ ط§ظ„ط¹ظ…ظٹظ„"""
    if not user.get("permissions", {}).get("can_manage_new_clients") and not user.get("permissions", {}).get("is_admin"):
        raise HTTPException(status_code=403, detail="ظ„ظٹط³ ظ„ط¯ظٹظƒ طµظ„ط§ط­ظٹط©")
        
    supabase = get_supabase_client()
    try:
        supabase.table("new_client_requests").update({"status": "rejected", "reviewed_by": user["id"]}).eq("id", request_id).execute()
        return {"status": "success", "message": "طھظ… ط±ظپط¶ ط§ظ„ط·ظ„ط¨ ط¨ظ†ط¬ط§ط­"}
    except Exception as e:
        return {"status": "error", "message": "ط­ط¯ط« ط®ط·ط£ ط£ط«ظ†ط§ط، ط§ظ„ط±ظپط¶"}
@router.get("/clients", response_class=HTMLResponse)
async def admin_clients(request: Request, user: dict = Depends(verify_admin)):
    """قائمة جميع العملاء النشطين"""
    try:
        supabase = get_supabase_client()
        res = supabase.table("clients").select("*").execute()
        return templates.TemplateResponse("admin_clients.html", {"request": request, "user": user, "clients": res.data})
    except Exception as e:
        return HTMLResponse(content=f"<h1>Error in clients page: {str(e)}</h1>", status_code=500)

@router.get("/subscriptions", response_class=HTMLResponse)
async def admin_subscriptions(request: Request, user: dict = Depends(verify_admin)):
    """إدارة اشتراكات العملاء"""
    try:
        return templates.TemplateResponse("admin_subscriptions.html", {"request": request, "user": user})
    except Exception as e:
        return HTMLResponse(content=f"<h1>Error in subscriptions page: {str(e)}</h1>", status_code=500)

@router.get("/users", response_class=HTMLResponse)
async def admin_users(request: Request, user: dict = Depends(verify_admin)):
    """إدارة موظفي النظام (الأدمن)"""
    try:
        supabase = get_supabase_client()
        res = supabase.table("sales_admin_users").select("*").execute()
        return templates.TemplateResponse("admin_users.html", {"request": request, "user": user, "admin_users": res.data})
    except Exception as e:
        return HTMLResponse(content=f"<h1>Error in users page: {str(e)}</h1>", status_code=500)
