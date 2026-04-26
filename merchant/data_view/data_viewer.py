# merchant/data_view/data_viewer.py
# عرض البيانات التي تمت مزامنتها
# يعرض البيانات المحفوظة في قاعدة بيانات العميل بشكل مرئي

def get_synced_data(client_id: str, page: int = 1, page_size: int = 50) -> dict:
    """يجلب البيانات مع pagination"""
    pass

def get_available_columns(client_id: str) -> list:
    pass
