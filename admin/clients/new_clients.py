# admin/clients/new_clients.py
# إدارة طلبات العملاء الجدد
# - يعرض الطلبات بحالة 'pending' فقط لمن يملك صلاحية can_manage_new_clients
# - عند القبول  -> ينقل العميل لجدول clients ثم لإدارة الاشتراكات
# - عند الرفض  -> يتحول لون العميل للأحمر مع منع التعديل (status='rejected')

def get_pending_requests():
    pass

def accept_client(request_id: str, reviewed_by: str):
    """تقبل الطلب وتنشئ سجلاً في جدول clients وتحوّل لإدارة الاشتراكات"""
    pass

def reject_client(request_id: str, reviewed_by: str):
    """ترفض الطلب وتضع status='rejected' مع منع التعديل"""
    pass
