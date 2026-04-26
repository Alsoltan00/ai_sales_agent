# merchant/home.py
# واجهة التاجر الرئيسية
# تُفتح فقط للعملاء الذين لديهم اشتراك ساري (status='active')
# تعرض جميع الأدوات المتاحة للتاجر

def load_merchant_home(client_id: str):
    """يتحقق من الاشتراك ثم يحمّل واجهة التاجر"""
    pass

def check_subscription_active(client_id: str) -> bool:
    pass
