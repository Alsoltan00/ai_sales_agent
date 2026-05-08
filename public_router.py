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
async def view_public_invoice(request: Request, order_id: str, tpl: str = "classic", color: str = "#4361ee", show_logo: str = "true", show_qr: str = "false", footer: str = ""):
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
                # Ensure qty and price are numbers to avoid Jinja2 math crash
                try: it["qty"] = float(it.get("qty") or it.get("كمية") or 1)
                except: it["qty"] = 1.0
                try: it["price"] = float(it.get("price") or it.get("سعر") or 0)
                except: it["price"] = 0.0
                clean_items.append(it)
            elif isinstance(it, str):
                clean_items.append({"name": it, "qty": 1.0, "price": 0.0})
                
        order["items"] = clean_items

        try:
            order["total_amount"] = float(order.get("total_amount") or 0)
        except:
            order["total_amount"] = 0.0

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
            "public_url": public_url,
            "tpl": tpl,
            "color": color,
            "show_logo": show_logo.lower() == "true",
            "show_qr": show_qr.lower() == "true",
            "footer": footer
        })

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"[ERROR] public invoice traceback:\n{error_details}")
        raise HTTPException(status_code=500, detail=f"حدث خطأ أثناء عرض الفاتورة: {str(e)}")
