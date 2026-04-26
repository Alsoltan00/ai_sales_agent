# merchant/authorized_numbers/number_manager.py
# واجهة الأرقام المصرّحة — بوابة الأمان
# القاعدة: أي رسالة من رقم غير مضاف -> لا تُحلَّل ولا تُرسَل ولا يُتعامل معها
# أزرار إضافية:
#   - عدم الرد على أي مجموعة  (block_groups=True)
#   - السماح بالرد على الكل   (allow_all=True)

def get_authorized_numbers(client_id: str) -> list:
    pass

def add_number(client_id: str, phone_number: str, label: str = ""):
    pass

def remove_number(client_id: str, phone_number: str):
    pass

def is_authorized(client_id: str, phone_number: str) -> bool:
    """الفلتر الرئيسي: هل هذا الرقم مسموح بالرد عليه؟"""
    pass

def set_block_groups(client_id: str, block: bool):
    """منع/السماح بالرد على المجموعات"""
    pass

def set_allow_all(client_id: str, allow: bool):
    """السماح بالرد على جميع الأرقام أو إلغاء السماح"""
    pass
