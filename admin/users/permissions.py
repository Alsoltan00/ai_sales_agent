# admin/users/permissions.py
# نظام الصلاحيات
# الصلاحيات المتاحة:
#   - can_manage_new_clients   : رؤية وقبول/رفض العملاء الجدد
#   - can_manage_subscriptions : إدارة الاشتراكات
#   - can_manage_users         : إضافة وتعديل المستخدمين (أدمن)
#   - is_admin                 : صلاحيات كاملة

PERMISSIONS = {
    "can_manage_new_clients": False,
    "can_manage_subscriptions": False,
    "can_manage_users": False,
    "is_admin": False,
}

def check_permission(user_permissions: dict, permission: str) -> bool:
    pass

def update_permissions(user_id: str, new_permissions: dict):
    pass
