# docs/api_reference.md
# مرجع API الكامل للنظام

## نقاط النهاية الرئيسية (Endpoints)

### المصادقة
POST /auth/login          — تسجيل الدخول
POST /auth/register       — إنشاء حساب جديد
POST /auth/logout         — تسجيل الخروج

### واجهة الإدارة
GET  /admin/clients/new          — جلب طلبات العملاء الجدد
POST /admin/clients/accept/{id}  — قبول عميل جديد
POST /admin/clients/reject/{id}  — رفض عميل جديد
GET  /admin/subscriptions        — جلب جميع الاشتراكات
PUT  /admin/subscriptions/{id}   — تحديث اشتراك
GET  /admin/users                — جلب جميع الموظفين
POST /admin/users                — إضافة موظف جديد
PUT  /admin/users/{id}           — تعديل موظف
DELETE /admin/users/{id}         — حذف موظف

### واجهة التاجر
GET  /merchant/store             — جلب إعدادات المتجر
PUT  /merchant/store             — تحديث إعدادات المتجر
GET  /merchant/planning          — جلب إعدادات التخطيط
PUT  /merchant/planning          — تحديث إعدادات التخطيط
GET  /merchant/ai-model          — جلب إعدادات النموذج
POST /merchant/ai-model/test     — اختبار النموذج
POST /merchant/ai-model/save     — حفظ النموذج (بعد الاختبار فقط)

### المزامنة
POST /merchant/sync/supabase     — ربط Supabase
POST /merchant/sync/aiven        — ربط Aiven
POST /merchant/sync/sheets       — ربط Google Sheets
GET  /merchant/sync/status       — حالة المزامنة
GET  /merchant/data              — عرض البيانات المزامنة

### الأرقام المصرّحة
GET  /merchant/numbers           — جلب الأرقام المصرّحة
POST /merchant/numbers           — إضافة رقم
DELETE /merchant/numbers/{phone} — حذف رقم
PUT  /merchant/numbers/settings  — تحديث إعدادات (block_groups, allow_all)

### Webhooks
POST /webhook/telegram           — webhook تيليجرام
POST /webhook/whatsapp-evolution — webhook واتساب Evolution
POST /webhook/whatsapp-official  — webhook واتساب الرسمي
GET  /webhook/whatsapp-official  — التحقق من webhook واتساب الرسمي
