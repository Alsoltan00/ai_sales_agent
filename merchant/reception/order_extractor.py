"""
merchant/reception/order_extractor.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
محرك استخراج الطلبات الذكي مع التحقق الصارم من اكتمال البيانات
- لا يُعتمد أي طلب إلا إذا كانت بياناته مكتملة بحسب نوع المتجر
- يدعم جميع المنصات (واتساب، تيليجرام، إنستجرام، تيك توك)
"""
import json
import re
import random
from datetime import datetime


# ─── الحقول المطلوبة حسب نوع المتجر ────────────────────────────────────────

# حقول مشتركة لجميع أنواع المتاجر (لا يقبل فراغاً)
_REQUIRED_ALWAYS = ["customer_name", "items"]

# حقول إضافية للمتاجر الفيزيائية فقط
_REQUIRED_PHYSICAL = ["customer_address", "customer_city"]

# حقول إضافية لمتاجر الحجز/الخدمات (رقم الهاتف يسحب تلقائياً لذلك لا داعي لاشتراطه على الذكاء الاصطناعي)
_REQUIRED_BOOKING = []


def validate_order_data(order_data: dict, delivery_type: str = "physical") -> tuple[bool, str]:
    """
    يتحقق من اكتمال بيانات الطلب قبل اعتماده.
    
    Args:
        order_data: بيانات الطلب المستخرجة من الذكاء الاصطناعي
        delivery_type: نوع التسليم ('physical', 'digital', 'booking')
    
    Returns:
        (True, "") إذا كانت البيانات مكتملة
        (False, "رسالة الخطأ") إذا كانت البيانات ناقصة
    """
    missing_fields = []

    # 1. التحقق من الحقول المشتركة دائماً
    for field in _REQUIRED_ALWAYS:
        val = order_data.get(field)
        if not val or (isinstance(val, str) and not val.strip()):
            if field == "customer_name":
                missing_fields.append("اسم العميل")
            elif field == "items":
                missing_fields.append("المنتجات المطلوبة")

    # تحقق إضافي: items يجب ألا تكون قائمة فارغة
    items = order_data.get("items", [])
    if isinstance(items, list) and len(items) == 0:
        missing_fields.append("المنتجات المطلوبة")

    # 2. التحقق من الحقول الإضافية حسب نوع التسليم
    if delivery_type == "physical":
        for field in _REQUIRED_PHYSICAL:
            val = order_data.get(field)
            if not val or (isinstance(val, str) and not val.strip()):
                if field == "customer_phone":
                    missing_fields.append("رقم الهاتف")
                elif field == "customer_address":
                    missing_fields.append("عنوان التوصيل")
                elif field == "customer_city":
                    missing_fields.append("المدينة")

    elif delivery_type in ("booking", "service"):
        for field in _REQUIRED_BOOKING:
            val = order_data.get(field)
            if not val or (isinstance(val, str) and not val.strip()):
                missing_fields.append("رقم الهاتف")

    if missing_fields:
        missing_str = "، ".join(missing_fields)
        return False, f"لا يمكن اعتماد الطلب - البيانات الناقصة: {missing_str}"

    return True, ""


def extract_order_json(ai_reply: str) -> tuple[dict | None, str]:
    """
    يستخرج بيانات الطلب من رد الذكاء الاصطناعي بطريقة ذكية.
    
    المشكلة القديمة: regex ({.*?}) كان يقطع JSON عند أول }] 
    داخل مصفوفة items بدلاً من نهاية الكائن الكامل.
    
    الحل: استخدام عداد أقواس (bracket counting) لإيجاد JSON الكامل.
    
    Returns:
        tuple: (order_data_dict أو None, ai_reply_cleaned)
    """
    # البحث عن بداية الوسم
    marker = "[ORDER_DATA:"
    start_idx = ai_reply.find(marker)
    if start_idx == -1:
        return None, ai_reply
    
    # إيجاد بداية الـ JSON (أول { بعد ORDER_DATA:)
    json_search_start = start_idx + len(marker)
    brace_start = ai_reply.find("{", json_search_start)
    if brace_start == -1:
        return None, ai_reply
    
    # عداد الأقواس لإيجاد نهاية JSON الكامل
    json_str = _extract_balanced_json(ai_reply, brace_start)
    if not json_str:
        return None, ai_reply
    
    # محاولة التحليل مع إصلاح تلقائي
    order_data = _safe_parse_json(json_str)
    if not order_data:
        return None, ai_reply
    
    # إيجاد نهاية الوسم الكامل لإزالته من الرد
    tag_end = ai_reply.find("]", brace_start + len(json_str))
    if tag_end != -1:
        full_tag = ai_reply[start_idx:tag_end + 1]
    else:
        full_tag = ai_reply[start_idx:]
    
    cleaned_reply = ai_reply.replace(full_tag, "").strip()
    
    return order_data, cleaned_reply


def _extract_balanced_json(text: str, start: int) -> str | None:
    """
    يستخرج كائن JSON كامل باستخدام عداد الأقواس المتوازن.
    يتعامل مع النصوص العربية والأقواس المتداخلة بشكل صحيح.
    """
    depth = 0
    in_string = False
    escape_next = False
    
    for i in range(start, len(text)):
        char = text[i]
        
        if escape_next:
            escape_next = False
            continue
        
        if char == '\\' and in_string:
            escape_next = True
            continue
        
        if char == '"' and not escape_next:
            in_string = not in_string
            continue
        
        if in_string:
            continue
        
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    
    return None


def _safe_parse_json(json_str: str) -> dict | None:
    """
    يحاول تحليل JSON مع عدة محاولات إصلاح تلقائية
    للتعامل مع الأخطاء الشائعة من نماذج الذكاء الاصطناعي.
    """
    # المحاولة 1: التحليل المباشر
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass
    
    # المحاولة 2: إصلاح الفواصل الزائدة (trailing commas)
    try:
        fixed = re.sub(r',\s*}', '}', json_str)
        fixed = re.sub(r',\s*\]', ']', fixed)
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass
    
    # المحاولة 3: إصلاح الاقتباسات المفردة
    try:
        fixed = json_str.replace("'", '"')
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass
    
    # المحاولة 4: إصلاح الأرقام العربية/الهندية
    try:
        arabic_digits = {'٠':'0', '١':'1', '٢':'2', '٣':'3', '٤':'4',
                        '٥':'5', '٦':'6', '٧':'7', '٨':'8', '٩':'9'}
        fixed = json_str
        for ar, en in arabic_digits.items():
            fixed = fixed.replace(ar, en)
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass
    
    # المحاولة 5: إزالة أحرف التحكم والأسطر الجديدة داخل النصوص
    try:
        fixed = re.sub(r'[\x00-\x1f]+', ' ', json_str)
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass
    
    print(f"[ORDER-EXTRACT] All JSON repair attempts failed for: {json_str[:200]}...")
    return None


def build_order_record(order_data: dict, client_id: str, phone: str,
                       channel: str, prefix: str = "AI") -> dict:
    """
    يبني سجل الطلب الكامل بتنسيق موحد لجميع القنوات.
    """
    order_num = f"{prefix}-{datetime.now().strftime('%y%m%d')}-{random.randint(1000, 9999)}"
    
    # تنظيف رقم الهاتف
    clean_phone = phone.split("@")[0].replace("+", "")
    
    # حساب الإجمالي من العناصر إذا لم يُذكر
    total = order_data.get("total_amount", 0)
    items = order_data.get("items", [])
    if not total and items:
        try:
            total = sum(
                float(item.get("price", 0)) * int(item.get("qty", 1))
                for item in items
            )
        except (ValueError, TypeError):
            total = 0
    
    return {
        "client_id": client_id,
        "order_number": order_num,
        "order_type": order_data.get("order_type", "purchase"),
        "customer_name": order_data.get("customer_name", "").strip(),
        "customer_phone": order_data.get("customer_phone") or clean_phone,
        "customer_address": order_data.get("customer_address", "").strip(),
        "customer_city": order_data.get("customer_city", "").strip(),
        "customer_notes": order_data.get("customer_notes", ""),
        "items": items,
        "total_amount": float(total),
        "payment_method": order_data.get("payment_method", ""),
        "channel": channel,
        "conversation_phone": phone,
        "ai_summary": f"تم تسجيله تلقائياً بواسطة الذكاء الاصطناعي عبر {channel}"
    }


def get_delivery_type_for_client(client_id: str) -> str:
    """
    يجلب نوع التسليم للتاجر من قاعدة البيانات.
    مُخزَّن مؤقتاً في الذاكرة لتجنب الاستعلامات المتكررة.
    """
    try:
        from database.db_client import get_db_client
        db = get_db_client()
        res = db.table("planning_config").select("delivery_type").eq("client_id", client_id).single().execute()
        if res.data:
            return res.data.get("delivery_type") or "physical"
    except Exception as e:
        print(f"[ORDER-EXTRACTOR] Error fetching delivery_type: {e}")
    return "physical"  # افتراضي: فيزيائي (الأكثر صرامة)
