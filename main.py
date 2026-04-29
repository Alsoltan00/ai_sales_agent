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
    print("[STARTUP] AI Sales Agent starting...")
    # إصلاح تلقائي لقاعدة البيانات في مهمة خلفية لعدم تعطيل بدء الخادم
    asyncio.create_task(run_db_migrations())

async def run_db_migrations():
    """تحديث قاعدة البيانات في الخلفية لضمان سرعة استجابة الخادم عند بدء التشغيل"""
    print("[DB] Starting database schema verification...")
    try:
        from database.db_client import get_db_engine
        from sqlalchemy import text, inspect
        engine = get_db_engine()
        if not engine:
            print("[DB] No engine found, skipping migrations.")
            return

        with engine.connect() as conn:
            inspector = inspect(engine)
            
            # 1. تحديث جدول العملاء
            columns = [c['name'] for c in inspector.get_columns('clients')]
            if 'ignore_groups' not in columns:
                conn.execute(text("ALTER TABLE clients ADD COLUMN ignore_groups BOOLEAN DEFAULT TRUE;"))
            if 'subscription_plan' not in columns:
                conn.execute(text("ALTER TABLE clients ADD COLUMN subscription_plan TEXT DEFAULT 'free';"))
            if 'subscription_ends_at' not in columns:
                conn.execute(text("ALTER TABLE clients ADD COLUMN subscription_ends_at TIMESTAMP;"))
            if 'messages_used' not in columns:
                conn.execute(text("ALTER TABLE clients ADD COLUMN messages_used INTEGER DEFAULT 0;"))

            # 2. تحديث جدول الاشتراكات
            try:
                sub_columns = [c['name'] for c in inspector.get_columns('subscriptions')]
                if 'messages_used' not in sub_columns:
                    conn.execute(text("ALTER TABLE subscriptions ADD COLUMN messages_used INTEGER DEFAULT 0;"))
            except: pass
                
            # 3. إنشاء الجداول المساعدة
            conn.execute(text("CREATE TABLE IF NOT EXISTS business_rules (id UUID PRIMARY KEY DEFAULT gen_random_uuid(), client_id UUID, rules_data JSONB, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS subscription_plans (id UUID PRIMARY KEY DEFAULT gen_random_uuid(), name TEXT NOT NULL, label_ar TEXT, price DECIMAL(10, 2) DEFAULT 0, duration_days INTEGER DEFAULT 30, permissions JSONB DEFAULT '{}', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS global_ai_models (id UUID PRIMARY KEY DEFAULT gen_random_uuid(), model_name TEXT NOT NULL, provider TEXT NOT NULL, api_key TEXT NOT NULL, model_id TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);"))

            # 4. إضافة خطط افتراضية إذا كان الجدول فارغاً
            try:
                count = conn.execute(text("SELECT count(*) FROM subscription_plans")).scalar()
                if count == 0:
                    conn.execute(text("""
                        INSERT INTO subscription_plans (name, label_ar, price, duration_days, permissions) VALUES 
                        ('basic', 'الأساسية', 0, 30, '{"max_models": 1, "voice_notes": false}'),
                        ('pro', 'الاحترافية', 100, 30, '{"max_models": 3, "voice_notes": true}'),
                        ('enterprise', 'الشركات', 500, 30, '{"max_models": 10, "voice_notes": true, "custom_support": true}')
                    """))
            except: pass

            # 5. تحديث جدول طلبات الانضمام
            try:
                req_columns = [c['name'] for c in inspector.get_columns('new_client_requests')]
                if 'email' not in req_columns:
                    conn.execute(text("ALTER TABLE new_client_requests ADD COLUMN email TEXT;"))
                if 'password_hash' not in req_columns:
                    conn.execute(text("ALTER TABLE new_client_requests ADD COLUMN password_hash TEXT;"))
                if 'store_link' not in req_columns:
                    conn.execute(text("ALTER TABLE new_client_requests ADD COLUMN store_link TEXT;"))
            except: pass
            
            conn.commit()
            print("[DB] Database schema verified successfully.")
    except Exception as e:
        print(f"[DB ERROR] Background migration failed: {e}")

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
