# admin/users/user_manager.py
# إدارة الموظفين داخل النظام
# - إضافة مستخدم جديد (فقط من لديه صلاحية admin)
# - تعديل بيانات مستخدم
# - تعيين الصلاحيات لكل مستخدم (تظهر على شكل جدول)
# - حذف مستخدم

def get_all_users():
    pass

def add_user(name: str, email: str, password: str, permissions: dict):
    pass

def update_user(user_id: str, data: dict):
    pass

def delete_user(user_id: str):
    pass
