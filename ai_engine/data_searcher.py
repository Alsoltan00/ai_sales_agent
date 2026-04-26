# ai_engine/data_searcher.py
# الخطوة 2 من خوارزمية الرد:
# البحث في قاعدة بيانات العميل بناءً على نتيجة التحليل وشروط التخطيط

def search_client_data(client_id: str, analysis_result: dict) -> list:
    """
    يبحث في جدول بيانات العميل بحسب:
    - الكيانات المستخرجة من الرسالة
    - الأعمدة المفعّلة فقط (غير الموقفة في واجهة التدريب)
    - الشروط المحددة في واجهة التخطيط
    Returns: قائمة بالنتائج المطابقة
    """
    pass

def get_active_columns(client_id: str) -> list:
    """يجلب الأعمدة المفعّلة فقط (is_disabled=False)"""
    pass
