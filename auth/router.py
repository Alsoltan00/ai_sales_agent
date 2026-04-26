from fastapi import APIRouter, Request, HTTPException, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from .login import authenticate_user
from .register import register_new_client
from .session_manager import create_session, destroy_session, get_current_user

router = APIRouter(tags=["Authentication"])
templates = Jinja2Templates(directory="templates")

class LoginRequest(BaseModel):
    contact_info: str # Could be email or contact_number
    password: str

class RegisterRequest(BaseModel):
    company_name: str
    contact_number: str

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    # Check if already logged in
    user = request.session.get("user")
    if user:
        if user.get("role") == "admin_user":
            return RedirectResponse(url="/admin/dashboard", status_code=303)
        else:
            return RedirectResponse(url="/merchant/home", status_code=303)
            
    return templates.TemplateResponse("login.html", {"request": request})

@router.post("/api/auth/login")
async def api_login(request: Request, payload: LoginRequest):
    user_data = authenticate_user(payload.contact_info, payload.password)
    
    if user_data:
        # Create session
        create_session(request, user_data)
        
        # Determine redirect url
        redirect_url = "/admin/dashboard" if user_data["user_type"] == "admin_user" else "/merchant/home"
        
        return {"status": "success", "redirect_url": redirect_url}
        
    return JSONResponse(
        status_code=401, 
        content={"status": "error", "message": "بيانات الدخول غير صحيحة"}
    )

@router.post("/api/auth/register")
async def api_register(payload: RegisterRequest):
    success, message = register_new_client(payload.company_name, payload.contact_number)
    if success:
        return {"status": "success", "message": message}
    return JSONResponse(
        status_code=400,
        content={"status": "error", "message": message}
    )

@router.get("/logout")
async def logout(request: Request):
    destroy_session(request)
    return RedirectResponse(url="/login", status_code=303)
