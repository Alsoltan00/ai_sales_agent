from database.db_client import get_supabase_client

def check_existing_account(contact_number: str, email: str = None) -> bool:
    """يتحدد مما إذا كان الرقم أو البريد مسجلاً بالفعل"""
    supabase = get_supabase_client()
    try:
        # التحقق من العملاء النشطين
        query_clients = supabase.table("clients").select("id").eq("contact_number", contact_number)
        if email:
            # التحقق من البريد أيضاً
            res_email = supabase.table("clients").select("id").eq("email", email).execute()
            if res_email.data: return True
            
        res_clients = query_clients.execute()
        if res_clients.data: return True
            
        # التحقق من الطلبات المعلقة
        query_req = supabase.table("new_client_requests").select("id").eq("contact_number", contact_number)
        if email:
            res_email_req = supabase.table("new_client_requests").select("id").eq("email", email).execute()
            if res_email_req.data: return True
            
        res_requests = query_req.execute()
        if res_requests.data: return True
            
    except Exception as e:
        print(f"Error checking existing account: {e}")
    return False

def register_new_client(company_name: str, contact_number: str, email: str = None, password: str = None, business_type: str = None, store_link: str = None) -> tuple[bool, str]:
    """يسجل طلب عميل جديد مع البيانات الموسعة"""
    if not company_name or not contact_number:
        return False, "يجب إدخال اسم الشركة ورقم التواصل"
        
    if check_existing_account(contact_number, email):
        return False, "بيانات الاتصال مسجلة بالفعل، يرجى تسجيل الدخول"
        
    supabase = get_supabase_client()
    try:
        from passlib.context import CryptContext
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        
        data = {
            "company_name": company_name,
            "contact_number": contact_number,
            "email": email,
            "business_type": business_type,
            "store_link": store_link,
            "status": "pending"
        }
        
        if password:
            data["password_hash"] = pwd_context.hash(password)
            
        supabase.table("new_client_requests").insert(data).execute()
        return True, "تم تسجيل طلبك بنجاح، سيتم مراجعته من قبل الإدارة"
    except Exception as e:
        print(f"Error registering new client: {e}")
        return False, f"حدث خطأ أثناء إرسال الطلب: {str(e)}"
