"""
merchant/reception/whatsapp_official_receiver.py
ط§ط³طھظ‚ط¨ط§ظ„ ط§ظ„ط±ط³ط§ط¦ظ„ ط¹ط¨ط± WhatsApp Cloud API ط§ظ„ط±ط³ظ…ظٹ ظ…ظ† Meta
"""
import httpx
from fastapi import APIRouter, Request, Response, Query
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
        client = supabase.table("clients").select("allow_all_numbers").eq("id", client_id).single().execute()
        if client.data and client.data.get("allow_all_numbers"):
            return True
        res = supabase.table("authorized_numbers").select("id").eq("client_id", client_id).eq("phone_number", phone).execute()
        return bool(res.data)
    except Exception:
        return False


async def _send_official_message(access_token: str, phone_number_id: str, to_phone: str, text: str):
    """ط¥ط±ط³ط§ظ„ ط±ط¯ ط¹ط¨ط± Meta Cloud API"""
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
async def verify_official_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify.token")
):
    """التحقق من Webhook عند ربطه مع Meta"""
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
async def official_webhook(request: Request):
    """Webhook ظ„ط§ط³طھظ‚ط¨ط§ظ„ ط±ط³ط§ط¦ظ„ ظˆط§طھط³ط§ط¨ ط§ظ„ط±ط³ظ…ظٹ"""
    try:
        body = await request.json()

        entry = body.get("entry", [])
        if not entry:
            return Response(status_code=200)

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

                    # ط§ظ„ط¨ط­ط« ط¹ظ† ط§ظ„طھط§ط¬ط±
                    cfg = _find_client_by_phone_id(phone_number_id)
                    if not cfg:
                        continue

                    client_id    = cfg["client_id"]
                    access_token = cfg["meta_access_token"]

                    # ط§ظ„طھط­ظ‚ظ‚ ظ…ظ† ط§ظ„طµظ„ط§ط­ظٹط©
                    if not _is_authorized(client_id, from_phone):
                        continue

                    # توليد الرد
                    ai_reply = await get_ai_response(
                        client_id=client_id,
                        phone_number=from_phone,
                        user_message=text,
                        channel="whatsapp_official"
                    )

                    # --- تفعيل الحفظ التلقائي للطلبات ---
                    from merchant.reception.order_extractor import extract_order_json, build_order_record
                    supabase = get_supabase_client()
                    
                    order_data, ai_reply = extract_order_json(ai_reply)
                    if order_data:
                        try:
                            final_order = build_order_record(order_data, client_id, from_phone, "whatsapp_official", "WA")
                            res = supabase.table("orders").insert(final_order).execute()
                            if res.data:
                                order_id = res.data[0]["id"]
                                host = request.headers.get("host", request.url.hostname)
                                scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
                                if host and ":" not in host and host != "localhost":
                                    scheme = "https"
                                invoice_url = f"{scheme}://{host}/invoice/{order_id}"
                                ai_reply += f"\n\n🧾 *رابط الفاتورة:*\n{invoice_url}"
                            print(f"[AUTO-ORDER] Order {final_order['order_number']} saved successfully for client {client_id}")
                        except Exception as e:
                            print(f"[AUTO-ORDER ERROR] Failed to save order: {e}")
                    # ----------------------------------

                    # اكتشاف الأزرار التفاعلية
                    from merchant.reception.buttons_handler import extract_buttons_from_reply, send_official_buttons
                    clean_reply, buttons = extract_buttons_from_reply(ai_reply)

                    # إرسال الرد
                    if buttons:
                        btn_sent = await send_official_buttons(access_token, phone_number_id, from_phone, clean_reply, buttons)
                        if not btn_sent:
                            await _send_official_message(access_token, phone_number_id, from_phone, clean_reply)
                    else:
                        await _send_official_message(access_token, phone_number_id, from_phone, clean_reply)

    except Exception as e:
        print(f"Official WhatsApp webhook error: {e}")

    return Response(status_code=200)
