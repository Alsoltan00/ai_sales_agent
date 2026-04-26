from fastapi import Request

def create_session(request: Request, user_data: dict):
    """
    يحفظ بيانات المستخدم في الجلسة
    user_data: dict يحتوي على (id, name, user_type, permissions, store_id/client_id)
    """
    request.session["user"] = {
        "id": str(user_data["id"]),
        "name": user_data.get("name", ""),
        "user_type": user_data["user_type"],
        "permissions": user_data.get("permissions", {})
    }

def get_current_user(request: Request) -> dict:
    """يسترجع المستخدم الحالي من الجلسة"""
    return request.session.get("user")

def destroy_session(request: Request):
    """ينهي الجلسة"""
    request.session.clear()
