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
            # التحقق من الأعمدة الموجودة وإضافتها إذا نقصت
            from sqlalchemy import inspect
            inspector = inspect(engine)
            columns = [c['name'] for c in inspector.get_columns('clients')]
            
            if 'ignore_groups' not in columns:
                try: conn.execute(text("ALTER TABLE clients ADD COLUMN ignore_groups BOOLEAN DEFAULT TRUE;"))
                except: pass
            if 'subscription_plan' not in columns:
                try: conn.execute(text("ALTER TABLE clients ADD COLUMN subscription_plan TEXT DEFAULT 'free';"))
                except: pass
            if 'subscription_ends_at' not in columns:
                try: conn.execute(text("ALTER TABLE clients ADD COLUMN subscription_ends_at TIMESTAMP;"))
                except: pass
                
            # إنشاء جدول قواعد العمل إذا لم يكن موجوداً
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS business_rules (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    client_id UUID,
                    rules_data JSONB,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))
            # إنشاء جدول خطط الاشتراك
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS subscription_plans (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    name TEXT NOT NULL,
                    label_ar TEXT,
                    price DECIMAL(10, 2) DEFAULT 0,
                    duration_days INTEGER DEFAULT 30,
                    permissions JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))
            # إضافة خطط افتراضية إذا كان الجدول فارغاً
            try:
                count = conn.execute(text("SELECT count(*) FROM subscription_plans")).scalar()
                if count == 0:
                    # نستخدم قيم نصية للمعرفات أو نتركها فارغة ليتم توليدها تلقائياً
                    conn.execute(text("""
                        INSERT INTO subscription_plans (name, label_ar, price, duration_days, permissions) VALUES 
                        ('basic', 'الأساسية', 0, 30, '{"max_models": 1, "voice_notes": false}'),
                        ('pro', 'الاحترافية', 100, 30, '{"max_models": 3, "voice_notes": true}'),
                        ('enterprise', 'الشركات', 500, 30, '{"max_models": 10, "voice_notes": true, "custom_support": true}')
                    """))
            except:
                pass
            # التحقق من الأعمدة في جدول طلبات الانضمام
            try:
                inspector = inspect(engine)
                req_columns = [c['name'] for c in inspector.get_columns('new_client_requests')]
                if 'email' not in req_columns:
                    try: conn.execute(text("ALTER TABLE new_client_requests ADD COLUMN email TEXT;"))
                    except: pass
                if 'password_hash' not in req_columns:
                    try: conn.execute(text("ALTER TABLE new_client_requests ADD COLUMN password_hash TEXT;"))
                    except: pass
                if 'business_type' not in req_columns:
                    try: conn.execute(text("ALTER TABLE new_client_requests ADD COLUMN business_type TEXT;"))
                    except: pass
                if 'store_link' not in req_columns:
                    try: conn.execute(text("ALTER TABLE new_client_requests ADD COLUMN store_link TEXT;"))
                    except: pass
            except:
                pass
                
            conn.commit()
            print("[DB] Database schema verified and updated.")
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
