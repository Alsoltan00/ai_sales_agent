from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from app.core.config import settings
from agent.database import authenticate_user, register_user

router = APIRouter()

@app.post("/login")
async def api_login(request: Request, payload: dict):
    username = payload.get("username")
    password = payload.get("password")
    user = authenticate_user(username, password)
    
    if user:
        if user.get("id") == -1:
            return {"status": "error", "message": user["status_error"]}
            
        request.session["user"] = {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "store_id": user["store_id"]
        }
        return {"status": "success"}
    return {"status": "error", "message": "اسم المستخدم أو كلمة المرور غير صحيحة"}

@router.post("/register")
async def api_register(payload: dict):
    username = payload.get("username")
    password = payload.get("password")
    if register_user(username, password):
        return {"status": "success"}
    return {"status": "error", "message": "اسم المستخدم موجود بالفعل"}

@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login")
