import os
import json
import asyncio
from fastapi import APIRouter, Request, HTTPException
from fastapi.templating import Jinja2Templates
from database.db_client import get_db_client
from merchant.planning.planning_config import get_planning_config

router = APIRouter()
supabase = get_db_client()

templates_dir = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=templates_dir)

@router.get("/print/{order_id}")
async def print_template(request: Request, order_id: str, template: str = "invoice_a4", color: str = "#4361ee", show_logo: str = "true", show_qr: str = "true", footer: str = ""):
    """Universal print endpoint - supports multiple template types and sizes"""
    try:
        order_res = await supabase.table("orders").select("*").eq("id", order_id).execute_async()
        if not order_res.data:
            raise HTTPException(status_code=404, detail="الطلب غير موجود")
        
        order = order_res.data[0]
        client_id = order.get("client_id")

        # Parse items
        items = order.get("items", [])
        if isinstance(items, str):
            try:
                items = json.loads(items)
            except:
                items = []
        if not isinstance(items, list):
            items = [items] if items else []
        
        clean_items = []
        for it in items:
            if isinstance(it, dict):
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

        # Client info
        client_res = await supabase.table("clients").select("company_name, logo_url, contact_number, email").eq("id", client_id).execute_async()
        client_info = client_res.data[0] if client_res.data else {}

        host = request.headers.get("host", request.url.hostname)
        scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
        if host and ":" not in host and host != "localhost":
            scheme = "https"
        public_url = f"{scheme}://{host}/invoice/{order_id}"

        # Valid templates
        valid_templates = [
            "invoice_a4", "invoice_thermal",
            "booking_a4", "booking_thermal", 
            "digital_a4", "digital_thermal"
        ]
        if template not in valid_templates:
            template = "invoice_a4"

        template_file = f"print/{template}.html"

        # Determine if digital product
        planning = await get_planning_config(client_id)
        is_digital = (planning.get("delivery_type") == "digital") if planning else False

        return templates.TemplateResponse(template_file, {
            "request": request,
            "order": order,
            "client": client_info,
            "public_url": public_url,
            "color": color,
            "show_logo": show_logo.lower() == "true",
            "show_qr": show_qr.lower() == "true",
            "footer": footer,
            "is_digital": is_digital
        })

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[ERROR] print template traceback:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"خطأ: {str(e)}")

@router.get("/invoice/{order_id}")
async def view_public_invoice(request: Request, order_id: str, tpl: str = "classic", color: str = "#4361ee", show_logo: str = "true", show_qr: str = "false", footer: str = ""):
    try:
        # Fetch order
        order_res = await supabase.table("orders").select("*").eq("id", order_id).execute_async()
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
        client_res = await supabase.table("clients").select("company_name, logo_url").eq("id", client_id).execute_async()
        client_info = client_res.data[0] if client_res.data else {}

        host = request.headers.get("host", request.url.hostname)
        scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
        if host and ":" not in host and host != "localhost":
            scheme = "https" # Force HTTPS in production
        public_url = f"{scheme}://{host}/invoice/{order_id}"

        # Determine if digital product
        planning = await get_planning_config(client_id)
        is_digital = (planning.get("delivery_type") == "digital") if planning else False

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
            "footer": footer,
            "is_digital": is_digital
        })

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"[ERROR] public invoice traceback:\n{error_details}")
        raise HTTPException(status_code=500, detail=f"حدث خطأ أثناء عرض الفاتورة: {str(e)}")

