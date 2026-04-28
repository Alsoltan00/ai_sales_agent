from database.db_client import get_supabase_client

def check_existing_account(contact_number: str) -> bool:
    """يتحدد مما إذا كان الرقم مسجلاً بالفعل كعميل أو طلب قيد الانتظار"""
    supabase = get_supabase_client()
    try:
        # Check in active clients
        res_clients = supabase.table("clients").select("id").eq("contact_number", contact_number).execute()
        if res_clients.data:
            return True
            
        # Check in pending requests
        res_requests = supabase.table("new_client_requests").select("id").eq("contact_number", contact_number).execute()
        if res_requests.data:
            return True
            
    except Exception as e:
        print(f"Error checking existing account: {e}")
        
    return False

def register_new_client(company_name: str, contact_number: str) -> tuple[bool, str]:
    """
    يسجل طلب عميل جديد
    يعيد (Success_boolean, Message)
    """
    if not company_name or not contact_number:
        return False, "يجب إدخال اسم الشركة ورقم التواصل"
        
    if check_existing_account(contact_number):
        return False, "هذا الرقم مسجل بالفعل، يرجى تسجيل الدخول"
        
    supabase = get_supabase_client()
    try:
        data = {
            "company_name": company_name,
            "contact_number": contact_number,
            "status": "pending"
        }
        supabase.table("new_client_requests").insert(data).execute()
        return True, "تم تسجيل طلبك بنجاح، سيتم مراجعته من قبل الإدارة"
    except Exception as e:
        print(f"Error registering new client: {e}")
        return False, "حدث خطأ أثناء إرسال الطلب، يرجى المحاولة لاحقاً"
