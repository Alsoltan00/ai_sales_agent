"""
merchant/reception/whatsapp_official_receiver.py
استقبال الرسائل عبر WhatsApp Cloud API الرسمي من Meta
"""
import httpx
from fastapi import APIRouter, Request, Response, Query, BackgroundTasks
from database.db_client import get_supabase_client
from merchant.ai_engine import get_ai_response

router = APIRouter(tags=["WhatsApp Official Webhook"])


def _find_client_by_phone_id(phone_number_id: str) -> dict | None:
    supabase = get_supabase_client()
    try:
        res = supabase.table("channels_config").select("*").eq("meta_phone_number_id", phone_number_id).single().execute()
        return res.data
    except Exception:
        return None


def _is_authorized(client_id: str, phone: str) -> bool:
    supabase = get_supabase_client()
    try:
        # Fetch client settings
        client = supabase.table("clients").select("allow_all_numbers, ignore_groups").eq("id", client_id).single().execute()
        allow_all = client.data.get("allow_all_numbers", False) if client.data else False
        ignore_groups = client.data.get("ignore_groups", True) if client.data else True

        # Check if it's a group message
        is_group = phone.endswith("@g.us")
        
        # 1. If it's a group and ignore_groups is ON, DENY
        if is_group and ignore_groups:
            return False

        clean_phone = phone.replace("@s.whatsapp.net", "").replace("@c.us", "").replace("@g.us", "")
        res = supabase.table("authorized_numbers").select("id").eq("client_id", client_id).eq("phone_number", clean_phone).execute()
        is_in_list = bool(res.data)

        if allow_all:
            if is_in_list:
                return False
            return True
        else:
            if is_in_list:
                return True
            return False
    except Exception:
        return False


async def _send_official_message(access_token: str, phone_number_id: str, to_phone: str, text: str):
    """إرسال رد عبر Meta Cloud API"""
    url = f"https://graph.facebook.com/v19.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_phone,
        "type": "text",
        "text": {"preview_url": False, "body": text}
    }
    async with httpx.AsyncClient() as client:
        await client.post(url, headers=headers, json=payload, timeout=15)


from fastapi.responses import PlainTextResponse

@router.get("/whatsapp/official")
@router.get("/whatsapp/official/")
async def verify_official_webhook(request: Request):
    """التحقق من Webhook عند ربطه مع Meta"""
    hub_mode = request.query_params.get("hub.mode")
    hub_challenge = request.query_params.get("hub.challenge")
    hub_verify_token = request.query_params.get("hub.verify.token")

    supabase = get_supabase_client()
    try:
        # البحث عن تاجر يملك هذا الـ verify_token
        res = supabase.table("channels_config").select("meta_verify_token").execute()
        valid_tokens = [row["meta_verify_token"] for row in (res.data or []) if row.get("meta_verify_token")]

        if hub_mode == "subscribe" and hub_verify_token in valid_tokens:
            return PlainTextResponse(content=hub_challenge, status_code=200)
    except Exception as e:
        print(f"Webhook verification error: {e}")

    return Response(status_code=403)


@router.post("/whatsapp/official")
async def official_webhook(request: Request, background_tasks: BackgroundTasks):
    """Webhook لاستقبال رسائل واتساب الرسمي"""
    try:
        body = await request.json()

        entry = body.get("entry", [])
        if not entry:
            return Response(status_code=200)

        host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.hostname
        scheme = request.headers.get("x-forwarded-proto") or request.url.scheme
        
        if host and (".onrender.com" in host or ".onrender.com" in str(request.url)):
            scheme = "https"
        elif host and ":" not in host and host != "localhost":
            scheme = "https"

        background_tasks.add_task(_process_official_webhook, body, host, scheme)

    except Exception as e:
        print(f"Official WhatsApp webhook routing error: {e}")

    return Response(status_code=200)

_phone_locks = {}
def _get_phone_lock(phone: str):
    if phone not in _phone_locks:
        import asyncio
        _phone_locks[phone] = asyncio.Lock()
    return _phone_locks[phone]

async def _process_official_webhook(body: dict, host: str, scheme: str):
    try:
        entry = body.get("entry", [])
        for ent in entry:
            for change in ent.get("changes", []):
                value = change.get("value", {})
                messages = value.get("messages", [])
                phone_number_id = value.get("metadata", {}).get("phone_number_id", "")

                for msg in messages:
                    msg_type = msg.get("type", "")
                    from_phone = msg.get("from", "")
                    text = ""

                    if msg_type == "text":
                        text = msg.get("text", {}).get("body", "")
                    elif msg_type == "interactive":
                        # معالجة ضغطات الأزرار التفاعلية
                        interactive = msg.get("interactive", {})
                        int_type = interactive.get("type", "")
                        if int_type == "button_reply":
                            text = interactive.get("button_reply", {}).get("title", "")
                        elif int_type == "list_reply":
                            text = interactive.get("list_reply", {}).get("title", "")
                    elif msg_type == "button":
                        text = msg.get("button", {}).get("text", "")
                    else:
                        continue

                    if not text or not from_phone:
                        continue

                    phone_lock = _get_phone_lock(from_phone)
                    await phone_lock.acquire()
                    try:
                        # البحث عن التاجر
                        cfg = _find_client_by_phone_id(phone_number_id)
                        if not cfg:
                            continue

                        client_id    = cfg["client_id"]
                        access_token = cfg["meta_access_token"]

                        # التحقق من الصلاحية
                        if not _is_authorized(client_id, from_phone):
                            continue

                        msg_id = msg.get("id", "")
                        if not msg_id:
                            import uuid
                            msg_id = str(uuid.uuid4())
                        
                        supabase = get_supabase_client()
                        
                        # حفظ رسالة المستخدم لتمكين الذاكرة
                        try:
                            supabase.table("message_logs").insert({
                                "client_id": client_id,
                                "message_id": str(msg_id),
                                "phone_number": from_phone,
                                "channel": "whatsapp_official",
                                "message_text": text,
                                "ai_response": ""
                            }).execute()
                        except Exception as e:
                            print(f"[WA OFF LOG] Error saving user message: {e}")

                        # توليد الرد
                        base_url = f"{scheme}://{host}"
                        ai_reply = await get_ai_response(
                            client_id=client_id,
                            phone_number=from_phone,
                            user_message=text,
                            channel="whatsapp_official",
                            base_url=base_url
                        )
                        
                        import re
                        if ai_reply:
                            # تنظيف تنسيق الماركدوان من Gemini وإزالة الهروب من الرموز
                            ai_reply = ai_reply.replace("\\_", "_")
                            # تحويل الماركدوان العريض (**) إلى واتساب العريض (*)
                            ai_reply = re.sub(r'\*\*(.*?)\*\*', r'*\1*', ai_reply)
                        
                        # تحديث رد الذكاء الاصطناعي في قاعدة البيانات للذاكرة
                        try:
                            supabase.table("message_logs").update({
                                "ai_response": ai_reply
                            }).eq("message_id", str(msg_id)).execute()
                        except Exception as e:
                            print(f"[WA OFF LOG] Error updating AI response: {e}")

                        # --- تفعيل الحفظ التلقائي للطلبات ---
                        from merchant.reception.order_extractor import extract_order_json, build_order_record, validate_order_data, get_delivery_type_for_client
                        supabase = get_supabase_client()
                        
                        order_data, ai_reply = extract_order_json(ai_reply)
                        if order_data:
                            try:
                                # ✅ التحقق الصارم من اكتمال البيانات قبل الاعتماد
                                delivery_type = get_delivery_type_for_client(client_id)
                                is_valid, error_msg = validate_order_data(order_data, delivery_type)
                                
                                if not is_valid:
                                    print(f"[AUTO-ORDER] REJECTED incomplete Official WA order: {error_msg}")
                                else:
                                    final_order = build_order_record(order_data, client_id, from_phone, "whatsapp_official", "WA")
                                    res = supabase.table("orders").insert(final_order).execute()
                                    if res.data:
                                        # --- تحديث بيانات العميل في CRM ---
                                        try:
                                            from merchant.customers.customer_manager import update_customer_data, increment_order_count
                                            updates = {}
                                            if order_data.get("customer_name"):
                                                updates["customer_name"] = order_data["customer_name"]
                                            if order_data.get("customer_address"):
                                                updates["customer_address"] = order_data["customer_address"]
                                            if order_data.get("customer_city"):
                                                updates["customer_city"] = order_data["customer_city"]
                                            if updates:
                                                update_customer_data(client_id, from_phone, updates)
                                            increment_order_count(client_id, from_phone)
                                        except Exception as crm_err:
                                            print(f"[CRM AUTO-UPDATE ERROR] Official WA: {crm_err}")

                                        order_id = res.data[0]["id"]
                                        invoice_url = f"{scheme}://{host}/invoice/{order_id}"
                                        ai_reply += f"\n\n🧾 *رابط الفاتورة:*\n{invoice_url}"
                                    print(f"[AUTO-ORDER] Official WA Order {final_order['order_number']} saved for client {client_id}")
                            except Exception as e:
                                print(f"[AUTO-ORDER ERROR] Official WA failed to save order: {e}")
                        # ----------------------------------

                        # اكتشاف الأزرار التفاعلية
                        from merchant.reception.buttons_handler import extract_buttons_from_reply, send_official_buttons
                        clean_reply, buttons = extract_buttons_from_reply(ai_reply)

                        # إرسال الرد
                        if buttons:
                            btn_sent = await send_official_buttons(access_token, phone_number_id, from_phone, clean_reply, buttons)
                            if not btn_sent:
                                # Fallback: إرسال كنص عادي وتضمين الخيارات كقائمة مرقمة
                                fallback_text = clean_reply + "\n\n"
                                for idx, btn in enumerate(buttons):
                                    fallback_text += f"*{idx + 1}-* {btn['text']}\n"
                                await _send_official_message(access_token, phone_number_id, from_phone, fallback_text.strip())
                        else:
                            await _send_official_message(access_token, phone_number_id, from_phone, clean_reply)

                    finally:
                        if 'phone_lock' in locals():
                            phone_lock.release()

    except Exception as e:
        print(f"Official WhatsApp webhook background task error: {e}")
