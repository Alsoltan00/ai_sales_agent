from database.db_client import get_supabase_client

def check_existing_account(contact_number: str, email: str = None) -> tuple[bool, str]:
    """يتحدد مما إذا كان الرقم أو البريد مسجلاً بالفعل، مع السماح بإعادة الطلب إذا رُفض"""
    supabase = get_supabase_client()
    try:
        # التحقق من العملاء النشطين
        res_phone = supabase.table("clients").select("id").eq("contact_number", contact_number).execute()
        if res_phone.data: return True, "رقم الجوال مسجل بالفعل كعميل نشط"
        
        if email:
            res_email = supabase.table("clients").select("id").eq("email", email).execute()
            if res_email.data: return True, "البريد الإلكتروني مسجل بالفعل كعميل نشط"
            
        # التحقق من الطلبات (المعلقة أو المقبولة فقط)
        res_phone_req = supabase.table("new_client_requests").select("id, status").eq("contact_number", contact_number).neq("status", "rejected").execute()
        if res_phone_req.data: return True, "لديك طلب سابق قيد المراجعة أو تم قبوله"
        
        if email:
            res_email_req = supabase.table("new_client_requests").select("id, status").eq("email", email).neq("status", "rejected").execute()
            if res_email_req.data: return True, "لديك طلب سابق بهذا البريد قيد المراجعة"
            
    except Exception as e:
        print(f"Error checking existing account: {e}")
    return False, ""
def validate_password(password: str) -> tuple[bool, str]:
    """يتحقق من قوة كلمة المرور"""
    if len(password) < 8:
        return False, "كلمة المرور يجب أن تكون 8 أحرف على الأقل"
    if len(password) > 64:
        return False, "كلمة المرور طويلة جداً، الحد الأقصى 64 حرفاً"
    import re
    if not re.search(r"[A-Z]", password):
        return False, "يجب أن تحتوي كلمة المرور على حرف كبير واحد على الأقل"
    if not re.search(r"\d", password):
        return False, "يجب أن تحتوي كلمة المرور على رقم واحد على الأقل"
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return False, "يجب أن تحتوي كلمة المرور على رمز خاص واحد على الأقل (!@#$%^&*...)"
    return True, ""

def register_new_client(company_name: str, contact_number: str, email: str = None, password: str = None, business_type: str = None, store_link: str = None) -> tuple[bool, str]:
    """يسجل طلب عميل جديد مع التحقق المفصل"""
    if not company_name or not contact_number:
        return False, "يجب إدخال اسم الشركة ورقم التواصل"
        
    if password:
        is_strong, error_msg = validate_password(password)
        if not is_strong:
            return False, error_msg
            
    exists, message = check_existing_account(contact_number, email)
    if exists:
        return False, message
        
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
            # Bcrypt has a 72-byte limit, we truncate to be safe
            data["password_hash"] = pwd_context.hash(password[:72])
            
        supabase.table("new_client_requests").insert(data).execute()
        return True, "تم تسجيل طلبك بنجاح، سيتم مراجعته من قبل الإدارة"
    except Exception as e:
        print(f"Error registering new client: {e}")
        return False, f"حدث خطأ أثناء إرسال الطلب: {str(e)}"
