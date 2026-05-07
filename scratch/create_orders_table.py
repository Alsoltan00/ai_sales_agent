"""
سكريبت إنشاء جدول الطلبات الشامل في Supabase
يتم تشغيله مرة واحدة فقط
"""
import os, sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db_client import get_supabase_client

def create_orders_table():
    supabase = get_supabase_client()
    
    # نحاول إنشاء سجل تجريبي لفحص وجود الجدول
    # إذا فشل يعني الجدول غير موجود ونحتاج إنشاءه من Supabase Dashboard
    
    print("=" * 60)
    print("📋 لإنشاء جدول الطلبات، قم بتنفيذ الأمر التالي في")
    print("   Supabase Dashboard → SQL Editor:")
    print("=" * 60)
    
    sql = """
-- ═══════════════════════════════════════════════════════════
-- جدول الطلبات الشامل - يدعم جميع أنواع الأنشطة التجارية
-- ═══════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS orders (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    
    -- معلومات الطلب الأساسية
    order_number TEXT NOT NULL,
    order_type TEXT DEFAULT 'purchase' CHECK (order_type IN ('purchase', 'return', 'booking', 'service', 'subscription', 'quote')),
    order_status TEXT DEFAULT 'pending' CHECK (order_status IN ('pending', 'confirmed', 'processing', 'shipped', 'delivered', 'completed', 'cancelled', 'refunded', 'on_hold')),
    
    -- بيانات العميل
    customer_name TEXT,
    customer_phone TEXT,
    customer_email TEXT,
    customer_address TEXT,
    customer_city TEXT,
    customer_region TEXT,
    customer_country TEXT DEFAULT 'SA',
    customer_notes TEXT,
    
    -- تفاصيل المنتجات/الخدمات (مصفوفة JSON)
    items JSONB DEFAULT '[]'::jsonb,
    
    -- الحسابات المالية
    subtotal NUMERIC(12,2) DEFAULT 0,
    discount_amount NUMERIC(12,2) DEFAULT 0,
    discount_code TEXT,
    tax_percentage NUMERIC(5,2) DEFAULT 0,
    tax_amount NUMERIC(12,2) DEFAULT 0,
    shipping_cost NUMERIC(12,2) DEFAULT 0,
    total_amount NUMERIC(12,2) DEFAULT 0,
    currency TEXT DEFAULT 'SAR',
    
    -- الدفع
    payment_method TEXT CHECK (payment_method IN ('cod', 'bank_transfer', 'payment_link', 'card', 'wallet', 'cash', 'other', NULL)),
    payment_status TEXT DEFAULT 'pending' CHECK (payment_status IN ('pending', 'paid', 'partial', 'refunded', 'failed')),
    payment_reference TEXT,
    paid_amount NUMERIC(12,2) DEFAULT 0,
    
    -- قناة الطلب
    channel TEXT DEFAULT 'whatsapp' CHECK (channel IN ('whatsapp', 'web', 'manual', 'api', 'telegram', 'instagram')),
    conversation_phone TEXT,
    
    -- الحجوزات والمواعيد
    booking_date DATE,
    booking_time TIME,
    booking_end_time TIME,
    booking_duration TEXT,
    booking_location TEXT,
    
    -- التوصيل والشحن
    delivery_method TEXT CHECK (delivery_method IN ('delivery', 'pickup', 'digital', 'in_store', NULL)),
    tracking_number TEXT,
    shipping_company TEXT,
    estimated_delivery DATE,
    
    -- ملاحظات إضافية
    internal_notes TEXT,
    ai_summary TEXT,
    
    -- الطوابع الزمنية
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    confirmed_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

-- فهارس للأداء
CREATE INDEX IF NOT EXISTS idx_orders_client_id ON orders(client_id);
CREATE INDEX IF NOT EXISTS idx_orders_order_number ON orders(order_number);
CREATE INDEX IF NOT EXISTS idx_orders_customer_phone ON orders(customer_phone);
CREATE INDEX IF NOT EXISTS idx_orders_order_status ON orders(order_status);
CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_orders_payment_status ON orders(payment_status);

-- تحديث updated_at تلقائياً
CREATE OR REPLACE FUNCTION update_orders_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_orders_updated_at ON orders;
CREATE TRIGGER trigger_orders_updated_at
    BEFORE UPDATE ON orders
    FOR EACH ROW
    EXECUTE FUNCTION update_orders_updated_at();

-- تمكين Row Level Security
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;

-- سياسة: السماح لجميع العمليات (يمكن تعديلها لاحقاً)
CREATE POLICY "Allow all operations on orders" ON orders FOR ALL USING (true) WITH CHECK (true);

SELECT 'تم إنشاء جدول الطلبات بنجاح ✅' AS result;
"""
    
    print(sql)
    print("=" * 60)
    print("✅ انسخ الأمر أعلاه والصقه في Supabase SQL Editor ثم اضغط Run")
    print("=" * 60)

if __name__ == "__main__":
    create_orders_table()
