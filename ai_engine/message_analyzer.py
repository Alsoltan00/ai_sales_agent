# ai_engine/message_analyzer.py
# الخطوة 1 من خوارزمية الرد:
# تحليل الرسالة الواردة وفهم معناها (NLU)
# لا تطابق أحرف فقط — يفهم المقصود الحقيقي من الرسالة

def analyze_message(client_id: str, message_text: str) -> dict:
    """
    يحلل الرسالة باستخدام النموذج المحدد للعميل
    Returns:
    {
        "intent": str,          # نية العميل (استفسار سعر، طلب منتج، سؤال عام...)
        "entities": dict,       # الكيانات المستخرجة (اسم المنتج، الكمية...)
        "is_off_topic": bool,   # هل السؤال خارج موضوع الشركة؟
        "raw_message": str
    }
    """
    pass

def is_identity_question(message_text: str) -> bool:
    """هل السؤال من نوع 'من أنت؟' أو ما يقاربها؟"""
    pass
