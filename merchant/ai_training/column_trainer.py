# merchant/ai_training/column_trainer.py
# تدريب النموذج على أعمدة بيانات العميل
# - يعرض الأعمدة المسحوبة من واجهة مزامنة البيانات
# - يمكن إضافة ملاحظة على كل عمود لشرح طريقة التعامل معه
# - زر إيقاف عمود: النموذج لا يُفكّر بداخله مهما حدث

def get_columns_with_config(client_id: str) -> list:
    """يجلب الأعمدة مع ملاحظاتها وحالة التفعيل"""
    pass

def update_column_note(client_id: str, column_name: str, note: str):
    pass

def toggle_column(client_id: str, column_name: str, is_disabled: bool):
    """تفعيل أو إيقاف عمود من تفكير النموذج"""
    pass
