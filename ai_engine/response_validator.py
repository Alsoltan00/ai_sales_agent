# ai_engine/response_validator.py
# الخطوة 3 من خوارزمية الرد:
# إعادة إرسال النتائج للنموذج للتحقق من أنها تناسب الشركة والعميل

def validate_response(client_id: str, original_message: str, search_results: list) -> dict:
    """
    يُرسل النتائج للنموذج للتحقق:
    - هل تطابق معايير الشركة؟
    - هل تطابق ما طلبه العميل فعلاً؟
    Returns:
    {
        "is_valid": bool,
        "validated_data": list,
        "reason": str
    }
    """
    pass
