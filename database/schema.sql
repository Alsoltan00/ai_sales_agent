-- database/schema.sql
-- هيكل قاعدة بيانات Supabase الكاملة

-- جدول المستخدمين (الموظفين)
CREATE TABLE IF NOT EXISTS sales_admin_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    permissions JSONB DEFAULT '{
        "can_manage_new_clients": false,
        "can_manage_subscriptions": false,
        "can_manage_users": false,
        "is_admin": false
    }',
    created_at TIMESTAMP DEFAULT NOW()
);

-- جدول العملاء / التجار
CREATE TABLE IF NOT EXISTS clients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_name TEXT NOT NULL,
    contact_number TEXT NOT NULL,
    email TEXT UNIQUE,
    password_hash TEXT,
    store_url TEXT,
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'paused', 'cancelled')),
    created_at TIMESTAMP DEFAULT NOW()
);

-- جدول الاشتراكات
CREATE TABLE IF NOT EXISTS subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    plan TEXT DEFAULT 'basic',
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'expired', 'paused')),
    messages_used INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

-- جدول طلبات الحسابات الجديدة
CREATE TABLE IF NOT EXISTS new_client_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_name TEXT NOT NULL,
    contact_number TEXT NOT NULL,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'rejected')),
    reviewed_by UUID REFERENCES sales_admin_users(id),
    reviewed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- جدول الأرقام المصرّحة
CREATE TABLE IF NOT EXISTS authorized_numbers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    phone_number TEXT NOT NULL,
    label TEXT DEFAULT '',
    block_groups BOOLEAN DEFAULT FALSE,
    allow_all BOOLEAN DEFAULT FALSE,
    added_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(client_id, phone_number)
);

-- جدول إعدادات نموذج الذكاء الاصطناعي
CREATE TABLE IF NOT EXISTS ai_models_config (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE UNIQUE,
    model_name TEXT NOT NULL,
    provider TEXT NOT NULL,
    api_key TEXT NOT NULL,
    model_id TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    is_working BOOLEAN DEFAULT FALSE,
    tested_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- جدول إعدادات المزامنة
CREATE TABLE IF NOT EXISTS sync_config (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    source_type TEXT CHECK (source_type IN ('supabase', 'aiven', 'google_sheets', 'excel')),
    connection_details JSONB NOT NULL,
    table_name TEXT,
    sheet_name TEXT,
    sync_interval_minutes INTEGER DEFAULT 5,
    last_synced_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- جدول إعدادات التخطيط (شخصية الوكيل)
CREATE TABLE IF NOT EXISTS planning_config (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE UNIQUE,
    company_description TEXT DEFAULT '',
    dialect_instructions TEXT DEFAULT '',
    sales_agent_name TEXT DEFAULT '',
    updated_at TIMESTAMP DEFAULT NOW()
);

-- جدول تدريب الأعمدة
CREATE TABLE IF NOT EXISTS column_training (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    column_name TEXT NOT NULL,
    note TEXT DEFAULT '',
    is_disabled BOOLEAN DEFAULT FALSE,
    UNIQUE(client_id, column_name)
);

-- جدول سجل الرسائل
CREATE TABLE IF NOT EXISTS message_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    channel TEXT CHECK (channel IN ('telegram', 'whatsapp_evolution', 'whatsapp_official')),
    direction TEXT CHECK (direction IN ('in', 'out')),
    phone_number TEXT NOT NULL,
    message_text TEXT,
    ai_response TEXT,
    timestamp TIMESTAMP DEFAULT NOW()
);
-- جدول إعدادات قنوات التواصل (الواتساب وتيليجرام)
CREATE TABLE IF NOT EXISTS channels_config (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE UNIQUE,
    telegram_bot_token TEXT,
    whatsapp_provider TEXT DEFAULT 'evolution',
    evolution_api_url TEXT,
    evolution_api_key TEXT,
    evolution_instance_name TEXT,
    meta_phone_number_id TEXT,
    meta_access_token TEXT,
    meta_verify_token TEXT,
    updated_at TIMESTAMP DEFAULT NOW()
);
-- تحديث جدول العملاء لإضافة خيار السماح للجميع
ALTER TABLE clients ADD COLUMN IF NOT EXISTS allow_all_numbers BOOLEAN DEFAULT FALSE;

-- جدول تخزين البيانات اليدوية (Excel/CSV)
CREATE TABLE IF NOT EXISTS merchant_manual_data (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE UNIQUE,
    data JSONB NOT NULL,
    filename TEXT,
    updated_at TIMESTAMP DEFAULT NOW()
);
