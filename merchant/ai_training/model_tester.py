# merchant/ai_training/model_tester.py
# اختبار نموذج الذكاء الاصطناعي قبل الحفظ
# القاعدة: لا يُحفظ النموذج إلا بعد التحقق الفعلي من أنه يعمل
# بعد الحفظ الناجح: تظهر علامة خضراء + مربعات اختبار

def test_model(provider: str, api_key: str, model_id: str) -> dict:
    """
    يختبر النموذج بإرسال رسالة تجريبية
    Returns: {"success": bool, "error": str | None, "response_time_ms": int}
    """
    pass

def save_model_config(client_id: str, provider: str, api_key: str, model_id: str, test_result: dict):
    """لا يحفظ إلا إذا كان test_result["success"] == True"""
    pass
