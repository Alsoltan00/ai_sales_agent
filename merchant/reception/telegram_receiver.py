"""
merchant/reception/telegram_receiver.py
استقبال الرسائل من تيليجرام عبر Webhook
"""
import json
import httpx
from fastapi import APIRouter, Request, Response
from database.db_client import get_supabase_client
from merchant.ai_engine import get_ai_response

router = APIRouter(tags=["Telegram Webhook"])


def _find_client_by_token(bot_token: str) -> dict | None:
    """البحث عن التاجر بواسطة رمز البوت"""
    supabase = get_supabase_client()
    try:
        res = supabase.table("channels_config").select("client_id").eq("telegram_bot_token", bot_token).single().execute()
        return res.data
    except Exception:
        return None





async def _send_telegram_message(bot_token: str, chat_id: int, text: str):
    """إرسال رد عبر تيليجرام"""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    async with httpx.AsyncClient() as client:
        await client.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)


@router.post("/telegram/{bot_token}")
async def telegram_webhook(bot_token: str, request: Request):
    """Webhook لاستقبال رسائل تيليجرام"""
    try:
        body = await request.json()
        
        # معالجة ضغطات الأزرار التفاعلية (Callback Query)
        callback = body.get("callback_query")
        if callback:
            cb_data = callback.get("data", "")
            cb_message = callback.get("message", {})
            chat_id = cb_message.get("chat", {}).get("id")
            if chat_id and cb_data:
                # إرسال تأكيد الضغطة لتيليجرام
                try:
                    async with httpx.AsyncClient() as client:
                        await client.post(
                            f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery",
                            json={"callback_query_id": callback["id"]},
                            timeout=5
                        )
                except: pass
                
                # تحويل نص الزر المعروض إلى رسالة عادية
                # نبحث عن نص الزر من inline_keyboard
                button_text = cb_data
                try:
                    reply_markup = cb_message.get("reply_markup", {})
                    for row in reply_markup.get("inline_keyboard", []):
                        for btn in row:
                            if btn.get("callback_data") == cb_data:
                                button_text = btn.get("text", cb_data)
                                break
                except: pass
                
                # إعادة معالجة كرسالة نصية عادية
                body["message"] = {
                    "chat": {"id": chat_id},
                    "from": callback.get("from", {}),
                    "text": button_text
                }
        
        message = body.get("message", {})
        if not message:
            return Response(status_code=200)

        chat_id     = message["chat"]["id"]
        text        = message.get("text", "")
        from_user   = message.get("from", {})
        phone_str   = str(chat_id)  # تيليجرام يستخدم chat_id كمعرف

        if not text:
            return Response(status_code=200)

        # البحث عن التاجر
        client_cfg = _find_client_by_token(bot_token)
        if not client_cfg:
            return Response(status_code=200)

        client_id = client_cfg["client_id"]

        msg_id = message.get("message_id", "")
        if not msg_id:
            import uuid
            msg_id = str(uuid.uuid4())
            
        supabase = get_supabase_client()
        
        # حفظ رسالة المستخدم لتمكين الذاكرة
        try:
            supabase.table("message_logs").insert({
                "client_id": client_id,
                "message_id": str(msg_id),
                "phone_number": phone_str,
                "channel": "telegram",
                "message_text": text,
                "ai_response": ""
            }).execute()
        except Exception as e:
            print(f"[TG LOG] Error saving user message: {e}")

        # توليد الرد
        ai_reply = await get_ai_response(
            client_id=client_id,
            phone_number=phone_str,
            user_message=text,
            channel="telegram"
        )
        
        # تحديث رد الذكاء الاصطناعي في قاعدة البيانات للذاكرة
        try:
            supabase.table("message_logs").update({
                "ai_response": ai_reply
            }).eq("message_id", str(msg_id)).execute()
        except Exception as e:
            print(f"[TG LOG] Error updating AI response: {e}")

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
                    print(f"[AUTO-ORDER] REJECTED incomplete Telegram order: {error_msg}")
                    # لا نحفظ الطلب - الذكاء الاصطناعي سيتابع جمع البيانات
                else:
                    final_order = build_order_record(order_data, client_id, phone_str, "telegram", "TG")
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
                                update_customer_data(client_id, phone_str, updates)
                            increment_order_count(client_id, phone_str)
                        except Exception as crm_err:
                            print(f"[CRM AUTO-UPDATE ERROR] Telegram: {crm_err}")

                        order_id = res.data[0]["id"]
                        host = request.headers.get("host", request.url.hostname)
                        scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
                        if host and ":" not in host and host != "localhost":
                            scheme = "https"
                        invoice_url = f"{scheme}://{host}/invoice/{order_id}"
                        ai_reply += f"\n\n🧾 رابط الفاتورة:\n{invoice_url}"
                    print(f"[AUTO-ORDER] Telegram Order {final_order['order_number']} saved for client {client_id}")
            except Exception as e:
                print(f"[AUTO-ORDER ERROR] Telegram failed to save order: {e}")
        # ----------------------------------

        # اكتشاف الأزرار التفاعلية
        from merchant.reception.buttons_handler import extract_buttons_from_reply, send_telegram_buttons
        clean_reply, buttons = extract_buttons_from_reply(ai_reply)

        # إرسال الرد
        if buttons:
            btn_sent = await send_telegram_buttons(bot_token, chat_id, clean_reply, buttons)
            if not btn_sent:
                await _send_telegram_message(bot_token, chat_id, clean_reply)
        else:
            await _send_telegram_message(bot_token, chat_id, clean_reply)

    except Exception as e:
        print(f"Telegram webhook error: {e}")

    return Response(status_code=200)
