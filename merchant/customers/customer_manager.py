"""
merchant/customers/customer_manager.py
إدارة بيانات العملاء (CRM) — البحث، الإنشاء، التحديث
"""
from database.db_client import get_db_client
from datetime import datetime


def get_or_create_customer(client_id: str, platform: str, platform_identifier: str, phone_number: str = None):
    """
    البحث عن عميل أو إنشاء سجل جديد له.
    - client_id: معرف التاجر
    - platform: المنصة (whatsapp / telegram / instagram)
    - platform_identifier: المعرف الرئيسي (رقم الهاتف أو اليوزر نيم)
    - phone_number: رقم الهاتف (تلقائي للواتساب)
    """
    db = get_db_client()
    try:
        # البحث عن العميل بالمعرف الرئيسي
        res = db.table("customer_profiles").select("*").eq(
            "client_id", client_id
        ).eq("platform_identifier", platform_identifier).single().execute()

        if res.data:
            return res.data  # العميل موجود مسبقاً

        # إنشاء سجل جديد للعميل
        new_customer = {
            "client_id": client_id,
            "platform": platform,
            "platform_identifier": platform_identifier,
            "phone_number": phone_number or (platform_identifier if platform.startswith("whatsapp") else None),
            "total_orders": 0,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        insert_res = db.table("customer_profiles").insert(new_customer).execute()
        if insert_res.data:
            print(f"[CRM] New customer created: {platform_identifier} on {platform}")
            return insert_res.data[0]
        return new_customer
    except Exception as e:
        print(f"[CRM ERROR] get_or_create_customer: {e}")
        return None


def update_customer_data(client_id: str, platform_identifier: str, updates: dict):
    """
    تحديث بيانات العميل (الاسم، العنوان، المدينة، الرقم).
    يُستخدم بعد إتمام الطلب أو عند تغيير البيانات.
    """
    db = get_db_client()
    try:
        updates["updated_at"] = datetime.now().isoformat()
        db.table("customer_profiles").update(updates).eq(
            "client_id", client_id
        ).eq("platform_identifier", platform_identifier).execute()
        print(f"[CRM] Customer {platform_identifier} updated: {list(updates.keys())}")
        return True
    except Exception as e:
        print(f"[CRM ERROR] update_customer_data: {e}")
        return False


def increment_order_count(client_id: str, platform_identifier: str):
    """زيادة عداد الطلبات بمقدار 1 بعد كل طلب ناجح"""
    db = get_db_client()
    try:
        # جلب العدد الحالي
        res = db.table("customer_profiles").select("total_orders").eq(
            "client_id", client_id
        ).eq("platform_identifier", platform_identifier).single().execute()

        current = res.data.get("total_orders", 0) if res.data else 0
        db.table("customer_profiles").update({
            "total_orders": current + 1,
            "updated_at": datetime.now().isoformat()
        }).eq("client_id", client_id).eq("platform_identifier", platform_identifier).execute()
        print(f"[CRM] Order count incremented for {platform_identifier}: {current + 1}")
        return True
    except Exception as e:
        print(f"[CRM ERROR] increment_order_count: {e}")
        return False


def get_all_customers(client_id: str):
    """جلب جميع العملاء للتاجر (للوحة التحكم)"""
    db = get_db_client()
    try:
        res = db.table("customer_profiles").select("*").eq(
            "client_id", client_id
        ).order("updated_at", desc=True).execute()
        return res.data or []
    except Exception as e:
        print(f"[CRM ERROR] get_all_customers: {e}")
        return []


def delete_customer(client_id: str, customer_id: str):
    """حذف عميل"""
    db = get_db_client()
    try:
        db.table("customer_profiles").delete().eq(
            "id", customer_id
        ).eq("client_id", client_id).execute()
        return True
    except Exception as e:
        print(f"[CRM ERROR] delete_customer: {e}")
        return False
