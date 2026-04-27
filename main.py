import os
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
import asyncio

# استيراد الإعدادات
from config.settings import PORT, HOST, DEBUG

# إنشاء تطبيق FastAPI
app = FastAPI(title="AI Sales Agent", version="2.0", description="نظام وكيل المبيعات الذكي")

# إعداد الجلسات
app.add_middleware(
    SessionMiddleware, 
    secret_key=os.getenv("SESSION_SECRET", "super-secret-sales-agent-key-12345"),
    max_age=86400 * 7 # 7 أيام
)

# استيراد المسارات (Routers)
from auth.router import router as auth_router
from admin.router import router as admin_router
from merchant.router import router as merchant_router

# Webhook Receivers
from merchant.reception.telegram_receiver import router as telegram_router
from merchant.reception.whatsapp_evolution_receiver import router as evolution_router
from merchant.reception.whatsapp_official_receiver import router as official_router

# تسجيل المسارات
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(merchant_router)

# تسجيل مستقبلات الويب هوك مع بادئة واضحة
app.include_router(telegram_router, prefix="/webhook")
app.include_router(evolution_router, prefix="/webhook")
app.include_router(official_router, prefix="/webhook")

@app.on_event("startup")
async def startup_event():
    print("[STARTUP] AI Sales Agent started successfully on port 8000.")
    # إصلاح تلقائي لقاعدة البيانات في حال وجود أعمدة مفقودة
    try:
        from database.db_client import get_db_engine
        from sqlalchemy import text
        engine = get_db_engine()
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE clients ADD COLUMN IF NOT EXISTS ignore_groups BOOLEAN DEFAULT TRUE;"))
            conn.commit()
            print("[DB] Database schema verified and updated (ignore_groups).")
    except Exception as e:
        print(f"[DB ERROR] Startup schema update failed: {e}")

@app.get("/", response_class=RedirectResponse)
async def root_redirect():
    """توجيه الجذر إلى صفحة تسجيل الدخول"""
    return RedirectResponse(url="/login")

@app.get("/health")
async def health_check():
    """مسار للتحقق من صحة الخادم (Render Health Check)"""
    return {"status": "ok"}

if __name__ == "__main__":
    print(f"Server is starting on {HOST}:{PORT}...")
    uvicorn.run("main:app", host=HOST, port=PORT, reload=DEBUG)
