import os
import json
from fastapi import APIRouter, Request, HTTPException
from fastapi.templating import Jinja2Templates
from database.db_client import get_db_client

router = APIRouter()
supabase = get_db_client()

templates_dir = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=templates_dir)

@router.get("/invoice/{order_id}")
async def view_public_invoice(request: Request, order_id: str):
    try:
        # Fetch order
        order_res = supabase.table("orders").select("*").eq("id", order_id).execute()
        if not order_res.data:
            raise HTTPException(status_code=404, detail="الفاتورة غير موجودة")
        
        order = order_res.data[0]
        client_id = order.get("client_id")

        # Parse items if it's string
        items = order.get("items", [])
        if isinstance(items, str):
            try:
                import json as _json
                items = _json.loads(items)
            except:
                items = []
        
        if not isinstance(items, list):
            items = [items] if items else []
            
        clean_items = []
        for it in items:
            if isinstance(it, dict):
                clean_items.append(it)
            elif isinstance(it, str):
                clean_items.append({"name": it, "qty": 1, "price": 0})
                
        order["items"] = clean_items

        # Fetch client info for logo
        client_res = supabase.table("clients").select("company_name, logo_url").eq("id", client_id).execute()
        client_info = client_res.data[0] if client_res.data else {}

        host = request.headers.get("host", request.url.hostname)
        scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
        if host and ":" not in host and host != "localhost":
            scheme = "https" # Force HTTPS in production
        public_url = f"{scheme}://{host}/invoice/{order_id}"

        return templates.TemplateResponse("public_invoice.html", {
            "request": request,
            "order": order,
            "client": client_info,
            "order_json": json.dumps(order, default=str),
            "public_url": public_url
        })

    except Exception as e:
        print(f"[ERROR] public invoice: {e}")
        raise HTTPException(status_code=500, detail="حدث خطأ أثناء عرض الفاتورة")
