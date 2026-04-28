from database.db_client import get_supabase_client

def check_details(phone, email):
    supabase = get_supabase_client()
    
    print(f"Checking Phone: {phone}")
    res_phone_client = supabase.table("clients").select("id").eq("contact_number", phone).execute()
    print(f"Clients with Phone: {res_phone_client.data}")
    
    res_phone_req = supabase.table("new_client_requests").select("id, status").eq("contact_number", phone).execute()
    print(f"Requests with Phone: {res_phone_req.data}")
    
    print(f"\nChecking Email: {email}")
    res_email_client = supabase.table("clients").select("id").eq("email", email).execute()
    print(f"Clients with Email: {res_email_client.data}")
    
    res_email_req = supabase.table("new_client_requests").select("id, status").eq("email", email).execute()
    print(f"Requests with Email: {res_email_req.data}")

if __name__ == "__main__":
    check_details("966579331312", "whatc555app@gmail.com")
