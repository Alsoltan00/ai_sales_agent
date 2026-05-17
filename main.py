import os
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
import asyncio

# استيراد الإعدادات
from config.settings import PORT, HOST, DEBUG

import concurrent.futures

# إنشاء تطبيق FastAPI
app = FastAPI(title="AI Sales Agent", version="2.0", description="نظام وكيل المبيعات الذكي")

# زيادة سعة مجمع خيوط المعالجة الافتراضي لمنع تجميد النظام
@app.on_event("startup")
async def setup_executor():
    loop = asyncio.get_running_loop()
    loop.set_default_executor(concurrent.futures.ThreadPoolExecutor(max_workers=60))

app.add_middleware(
    SessionMiddleware, 
    secret_key=os.getenv("SESSION_SECRET", "super-secret-sales-agent-key-12345"),
    max_age=86400 * 7
)




# استيراد المسارات (Routers)
from auth.router import router as auth_router
from admin.router import router as admin_router
from merchant.router import router as merchant_router
from public_router import router as public_router

# Webhook Receivers
from merchant.reception.telegram_receiver import router as telegram_router
from merchant.reception.whatsapp_evolution_receiver import router as evolution_router
from merchant.reception.whatsapp_official_receiver import router as official_router

# تسجيل المسارات
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(merchant_router)
app.include_router(public_router)

# تسجيل مستقبلات الويب هوك مع بادئة واضحة
app.include_router(telegram_router, prefix="/webhook")
app.include_router(evolution_router, prefix="/webhook")
app.include_router(official_router, prefix="/webhook")

# ─── Static Files ─────────────────────────────────────────────────────────────
_static_path = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(_static_path):
    app.mount("/static", StaticFiles(directory=_static_path), name="static")


@app.on_event("startup")
async def startup_event():
    print("[STARTUP] AI Sales Agent starting...")
    # إصلاح تلقائي لقاعدة البيانات في مهمة خلفية في Thread منفصل لعدم تجميد الخادم
    asyncio.create_task(asyncio.to_thread(_migrate_database))

def _migrate_database():
    """تحديث قاعدة البيانات في الخلفية بطريقة آمنة لا تعيق تسجيل الدخول"""
    import time
    m_start = time.time()
    print("[DB] Checking schema updates...")
    try:
        from database.db_client import get_db_engine
        from sqlalchemy import text, inspect
        engine = get_db_engine()
        if not engine: return

        inspector = inspect(engine)
        table_names = inspector.get_table_names()

        # 1. تحديث جدول العملاء
        if 'clients' in table_names:
            with engine.begin() as conn:
                columns = [c['name'] for c in inspector.get_columns('clients')]
                updates = [
                    ('ignore_groups', 'BOOLEAN DEFAULT TRUE'),
                    ('subscription_plan', "TEXT DEFAULT 'free'"),
                    ('subscription_ends_at', 'TIMESTAMP'),
                    ('messages_used', 'INTEGER DEFAULT 0'),
                    ('logo_url', 'TEXT'),
                    ('onboarding_completed', 'BOOLEAN DEFAULT FALSE')
                ]
                for col, sql_type in updates:
                    if col not in columns:
                        conn.execute(text(f"ALTER TABLE clients ADD COLUMN {col} {sql_type};"))

        # 2. إنشاء جداول أساسية
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE IF NOT EXISTS business_rules (id UUID PRIMARY KEY DEFAULT gen_random_uuid(), client_id UUID, rules_data JSONB, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS subscription_plans (id UUID PRIMARY KEY DEFAULT gen_random_uuid(), name TEXT NOT NULL, label_ar TEXT, price DECIMAL(10, 2) DEFAULT 0, duration_days INTEGER DEFAULT 30, permissions JSONB DEFAULT '{}', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS global_ai_models (id UUID PRIMARY KEY DEFAULT gen_random_uuid(), model_name TEXT NOT NULL, provider TEXT NOT NULL, api_key TEXT NOT NULL, model_id TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);"))
        
        # 3. تحديث جدول التخطيط
        if 'planning_config' in table_names:
            with engine.begin() as conn:
                pc_cols = [c['name'] for c in inspector.get_columns('planning_config')]
                for col, sql_type in [
                    ('store_activity', 'TEXT'),
                    ('sales_type', 'TEXT'),
                    ('order_flow', 'TEXT'),
                    ('delivery_type', "TEXT DEFAULT 'physical'"),
                    ('custom_instructions', "TEXT DEFAULT ''"),
                    ('ai_temperature', "NUMERIC(3,2) DEFAULT 0.10"),
                    ('ai_max_tokens', "INTEGER DEFAULT 600"),
                    ('ai_core_strategy', "TEXT DEFAULT ''")
                ]:
                    if col not in pc_cols:
                        conn.execute(text(f"ALTER TABLE planning_config ADD COLUMN {col} {sql_type};"))

        # 4. جدول الطلبات
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS orders (
                    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                    client_id UUID,
                    order_number TEXT NOT NULL,
                    order_type TEXT DEFAULT 'purchase',
                    order_status TEXT DEFAULT 'pending',
                    customer_name TEXT,
                    customer_phone TEXT,
                    customer_email TEXT,
                    customer_address TEXT,
                    customer_city TEXT,
                    customer_region TEXT,
                    customer_country TEXT DEFAULT 'SA',
                    customer_notes TEXT,
                    items JSONB DEFAULT '[]',
                    subtotal NUMERIC(12,2) DEFAULT 0,
                    discount_amount NUMERIC(12,2) DEFAULT 0,
                    discount_code TEXT,
                    tax_percentage NUMERIC(5,2) DEFAULT 0,
                    tax_amount NUMERIC(12,2) DEFAULT 0,
                    shipping_cost NUMERIC(12,2) DEFAULT 0,
                    total_amount NUMERIC(12,2) DEFAULT 0,
                    currency TEXT DEFAULT 'SAR',
                    payment_method TEXT,
                    payment_status TEXT DEFAULT 'pending',
                    payment_reference TEXT,
                    paid_amount NUMERIC(12,2) DEFAULT 0,
                    channel TEXT DEFAULT 'whatsapp',
                    conversation_phone TEXT,
                    booking_date DATE,
                    booking_time TIME,
                    booking_end_time TIME,
                    booking_duration TEXT,
                    booking_location TEXT,
                    delivery_method TEXT,
                    tracking_number TEXT,
                    shipping_company TEXT,
                    estimated_delivery DATE,
                    internal_notes TEXT,
                    ai_summary TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
            """))

        # 5. جداول الشحن والخطط
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE IF NOT EXISTS shipping_config (id UUID DEFAULT gen_random_uuid() PRIMARY KEY, client_id UUID UNIQUE, free_shipping_city TEXT, free_shipping_min NUMERIC(12,2) DEFAULT 0, updated_at TIMESTAMPTZ DEFAULT NOW());"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS shipping_zones (id UUID DEFAULT gen_random_uuid() PRIMARY KEY, client_id UUID, zone_name TEXT NOT NULL, shipping_price NUMERIC(12,2) DEFAULT 0, free_shipping_enabled BOOLEAN DEFAULT FALSE, free_shipping_min NUMERIC(12,2) DEFAULT 0, created_at TIMESTAMPTZ DEFAULT NOW());"))
            
            # خطط افتراضية
            count = conn.execute(text("SELECT count(*) FROM subscription_plans")).scalar()
            if count == 0:
                conn.execute(text("""
                    INSERT INTO subscription_plans (name, label_ar, price, duration_days, permissions) VALUES 
                    ('basic', 'الأساسية', 0, 30, '{"max_models": 1}'),
                    ('pro', 'الاحترافية', 100, 30, '{"max_models": 3}'),
                    ('enterprise', 'الشركات', 500, 30, '{"max_models": 10}')
                """))

        print(f"[DB] Schema verification completed successfully in {time.time() - m_start:.2f}s.")
    except Exception as e:
        print(f"[DB ERROR] Migration failed: {e}")

@app.get("/", response_class=RedirectResponse)
async def root_redirect():
    """توجيه الجذر إلى صفحة تسجيل الدخول"""
    return RedirectResponse(url="/login")

@app.get("/health")
async def health_check():
    """مسار للتحقق من صحة الخادم وقاعدة البيانات (Keep-Alive)"""
    def _check_db():
        try:
            from database.db_client import get_db_engine
            from sqlalchemy import text
            engine = get_db_engine()
            if engine:
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                return "ok"
            return "no_engine"
        except Exception as e:
            return f"error: {str(e)}"
    
    db_status = await asyncio.to_thread(_check_db)
    return {"status": "ok", "db": db_status}

if __name__ == "__main__":
    print(f"Server is starting on {HOST}:{PORT}...")
    uvicorn.run("main:app", host=HOST, port=PORT, reload=DEBUG)

