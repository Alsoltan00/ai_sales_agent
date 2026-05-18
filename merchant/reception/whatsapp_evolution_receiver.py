"""
merchant/reception/whatsapp_evolution_receiver.py
استقبال الرسائل من واتساب عبر Evolution API
"""
import httpx
from fastapi import APIRouter, Request, Response, BackgroundTasks
from database.db_client import get_supabase_client
from merchant.ai_engine import get_ai_response

router = APIRouter(tags=["WhatsApp Evolution Webhook"])

# In-memory lock to prevent duplicate processing of the same message
_processing_ids: set = set()

async def _find_client_by_instance(instance_name: str) -> dict | None:
    supabase = get_supabase_client()
    try:
        res = await supabase.table("channels_config").select("*").eq("evolution_instance_name", instance_name).single().execute_async()
        return res.data
    except Exception:
        return None


async def _is_authorized(client_id: str, phone: str) -> bool:
    supabase = get_supabase_client()
    try:
        # Fetch client settings
        client = await supabase.table("clients").select("allow_all_numbers, ignore_groups").eq("id", client_id).single().execute_async()
        allow_all = client.data.get("allow_all_numbers", False) if client.data else False
        ignore_groups = client.data.get("ignore_groups", True) if client.data else True

        # Check if it's a group message
        is_group = phone.endswith("@g.us")
        
        # 1. If it's a group and ignore_groups is ON, DENY
        if is_group and ignore_groups:
            print(f"[AUTH] Ignoring GROUP message from {phone}")
            return False

        # Normalize phone: remove suffix
        clean_phone = phone.replace("@s.whatsapp.net", "").replace("@c.us", "").replace("@g.us", "")
        res = await supabase.table("authorized_numbers").select("id").eq("client_id", client_id).eq("phone_number", clean_phone).execute_async()
        is_in_list = bool(res.data)

        if allow_all:
            # القائمة تعمل كـ "قائمة حظر" (Blacklist)
            if is_in_list:
                print(f"[AUTH] Number {phone} is BLACKLISTED.")
                return False
            return True
        else:
            # القائمة تعمل كـ "قائمة بيضاء" (Whitelist)
            if is_in_list:
                return True
            print(f"[AUTH] Number {phone} is NOT in the whitelist.")
            return False
    except Exception as e:
        print(f"[AUTH ERROR] {e}")
        return False


async def _send_evolution_message(api_url: str, api_key: str, instance_name: str, phone: str, text: str) -> bool:
    """إرسال رد نصي عبر Evolution API بأسرع وقت ممكن وبدون تأخير إضافي"""
    clean_number = phone.split("@")[0]
    url = f"{api_url.rstrip('/')}/message/sendText/{instance_name}"
    headers = {"apikey": api_key, "Content-Type": "application/json"}
    
    payload = {
        "number": clean_number,
        "text": text,
        "options": {
            "delay": 0, 
            "linkPreview": False
        }
    }
    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(url, json=payload, headers=headers, timeout=15)
            return res.status_code < 400
    except Exception as e:
        print(f"[SEND ERROR] {e}")
        return False


async def _send_evolution_audio(api_url: str, api_key: str, instance_name: str, phone: str, audio_b64: str) -> bool:
    """إرسال رد صوتي عبر Evolution API"""
    clean_number = phone.split("@")[0]
    url = f"{api_url.rstrip('/')}/message/sendWhatsAppAudio/{instance_name}"
    headers = {"apikey": api_key, "Content-Type": "application/json"}
    payload = {
        "number": clean_number,
        "audio": audio_b64, # base64 string
        "options": {"delay": 1200, "presence": "recording"}
    }
    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(url, json=payload, headers=headers, timeout=30)
            return res.status_code < 400
    except Exception as e:
        print(f"[AUDIO SEND ERROR] {e}")
        return False


async def _send_typing_indicator(api_url: str, api_key: str, instance_name: str, phone: str):
    """إرسال إشعار 'جاري الكتابة' و'متصل' أثناء تفكير الذكاء الاصطناعي"""
    clean_number = phone.split("@")[0]
    base = api_url.rstrip('/')
    headers = {"apikey": api_key, "Content-Type": "application/json"}
    
    try:
        async with httpx.AsyncClient() as client:
            # 1. إجبار البوت على الظهور كـ "متصل" (Online)
            await client.post(
                f"{base}/chat/sendPresence/{instance_name}",
                json={"number": clean_number, "presence": "available"},
                headers=headers,
                timeout=5
            )
            
            # 2. إظهار حالة "جاري الكتابة..." لمدة تصل إلى 10 ثوانٍ (أثناء توليد الرد)
            await client.post(
                f"{base}/chat/sendPresence/{instance_name}",
                json={"number": clean_number, "presence": "composing", "delay": 10000},
                headers=headers,
                timeout=5
            )
            print(f"[TYPING] Triggered composing for {clean_number}")
    except Exception as e:
        print(f"[TYPING ERROR] {e}")


@router.post("/whatsapp/evolution/{instance_name}")
async def evolution_webhook(instance_name: str, request: Request, background_tasks: BackgroundTasks):
    """Webhook لاستقبال رسائل واتساب عبر Evolution API"""
    try:
        body = await request.json()
        print(f"[DEBUG] Received Webhook for instance: {instance_name}")

        # Evolution API sends different event types
        event = body.get("event", "")
        
        # معالجة حدث تسجيل الخروج من واتساب
        if event in ("connection.update", "CONNECTION_UPDATE"):
            data = body.get("data", {})
            state = data.get("state", "")
            reason = data.get("statusReason")
            
            # إذا قام المستخدم بتسجيل الخروج (Logout) أو تم إغلاق الجلسة بشكل غير طبيعي
            # statusReason 401: Unauthorized (Logged out)
            if state == "close" and reason in (401, 403, 405):
                print(f"[EVOLUTION] User logged out from instance {instance_name}. Triggering auto-delete.")
                cfg = await _find_client_by_instance(instance_name)
                if cfg and "client_id" in cfg:
                    from merchant.evolution_service import disconnect_instance
                    import asyncio
                    asyncio.create_task(disconnect_instance(cfg["client_id"]))
                return Response(status_code=200)
            return Response(status_code=200)
            
        if event not in ("messages.upsert", "MESSAGES_UPSERT"):
            return Response(status_code=200)

        # إعداد متغيرات الروابط للفاتورة قبل إرسالها للمهمة الخلفية
        # الأولوية لـ x-forwarded-host لأنه يحمل النطاق العام في Render/Nginx
        host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.hostname
        scheme = request.headers.get("x-forwarded-proto") or request.url.scheme
        
        # تصحيح البروتوكول في البيئات الإنتاجية
        if host and (".onrender.com" in host or ".onrender.com" in str(request.url)):
            scheme = "https"
        elif host and ":" not in host and host != "localhost":
            scheme = "https"

        base_url = f"{scheme}://{host}"

        # إضافة المعالجة إلى المهام الخلفية لضمان إرجاع استجابة 200 فوراً وتجنب إعادة الإرسال (Retries) من الخادم
        background_tasks.add_task(_process_evolution_message, instance_name, body, host, scheme, base_url)

    except Exception as e:
        print(f"[CRITICAL ERROR] Evolution webhook routing error: {e}")

    return Response(status_code=200)

_phone_locks = {}
def _get_phone_lock(phone: str):
    if phone not in _phone_locks:
        import asyncio
        _phone_locks[phone] = asyncio.Lock()
    return _phone_locks[phone]

async def _process_evolution_message(instance_name: str, body: dict, host: str, scheme: str, base_url: str):
    msg_id = None
    try:
        data = body.get("data", {})
        key  = data.get("key", {})
        supabase = get_supabase_client()

        # تجاهل الرسائل الصادرة من الجهاز نفسه
        if key.get("fromMe", False):
            return

        phone       = key.get("remoteJid", "")
        msg_id      = key.get("id")
        msg_content = data.get("message", {})

        phone_lock = _get_phone_lock(phone)
        await phone_lock.acquire()
        # 1. منع التكرار - المستوى الأول: ذاكرة داخلية (سريعة جداً)
        if msg_id:
            if msg_id in _processing_ids:
                print(f"[DEDUP] In-memory block: {msg_id}")
                return
            _processing_ids.add(msg_id)
            
            # المستوى الثاني: فحص قاعدة البيانات (للتأكد بعد إعادة التشغيل)
            try:
                check_dup = await supabase.table("message_logs").select("id").eq("message_id", msg_id).execute_async()
                if check_dup.data and len(check_dup.data) > 0:
                    print(f"[DEDUP] DB block: {msg_id}")
                    _processing_ids.discard(msg_id)
                    return
            except Exception as dup_err:
                print(f"[DEDUP] DB check error: {dup_err}")

        # جلب إعدادات العميل مبكراً لإرسال إشعار الكتابة فوراً
        cfg = await _find_client_by_instance(instance_name)
        if not cfg or "client_id" not in cfg:
            print(f"[ERROR] No client found for instance: {instance_name}")
            return
            
        client_id = cfg["client_id"]
        api_url = cfg["evolution_api_url"]
        api_key = cfg["evolution_api_key"]

        # ⚡ تشغيل إشعار "جاري الكتابة" فوراً جداً ليغطي وقت تحميل وتحويل الصوت والتفكير
        try:
            import asyncio
            asyncio.create_task(_send_typing_indicator(api_url, api_key, instance_name, phone))
        except:
            pass

        # التحقق من نوع الرسالة
        msg_type = "text"
        if "audioMessage" in msg_content:
            msg_type = "audio"
        elif "imageMessage" in msg_content:
            msg_type = "image"
        elif "videoMessage" in msg_content:
            msg_type = "video"

        # استخراج النص أو الرسالة الصوتية
        text = ""
        if msg_type == "text":
            text = msg_content.get("conversation") or \
                   msg_content.get("extendedTextMessage", {}).get("text") or ""
            
            # معالجة ضغطات الأزرار التفاعلية
            if not text and "buttonsResponseMessage" in msg_content:
                text = msg_content["buttonsResponseMessage"].get("selectedDisplayText") or \
                       msg_content["buttonsResponseMessage"].get("selectedButtonId") or ""
            if not text and "buttonResponseMessage" in msg_content:
                text = msg_content["buttonResponseMessage"].get("selectedDisplayText") or \
                       msg_content["buttonResponseMessage"].get("selectedButtonId") or ""
            # معالجة ردود القوائم التفاعلية
            if not text and "listResponseMessage" in msg_content:
                text = msg_content["listResponseMessage"].get("title") or \
                       msg_content["listResponseMessage"].get("singleSelectReply", {}).get("selectedRowId") or ""
        else:
            # للرسائل غير النصية، نأخذ الوصف (Caption) فقط إذا وجد
            text = msg_content.get("imageMessage", {}).get("caption") or \
                   msg_content.get("videoMessage", {}).get("caption") or ""

        # 2. معالجة الرسائل الصوتية والصور
        image_base64 = None
        audio_base64 = None
        if msg_type in ("audio", "image"):
            print(f"[DEBUG] {msg_type.capitalize()} message detected from {phone}. Downloading...")
            cfg = await _find_client_by_instance(instance_name)
            if cfg:
                try:
                    fetch_url = f"{cfg['evolution_api_url'].rstrip('/')}/chat/getBase64FromMediaMessage/{instance_name}"
                    msg_id = key.get("id")
                    media_payload = {"message": {"key": {"id": msg_id}}}
                    headers = {"apikey": cfg["evolution_api_key"]}
                    
                    async with httpx.AsyncClient() as client:
                        media_res = await client.post(fetch_url, json=media_payload, headers=headers, timeout=25)
                        
                        if media_res.status_code in [200, 201]:
                            media_data = media_res.json()
                            b64_data = media_data.get("base64")
                            
                            if b64_data:
                                if "," in str(b64_data):
                                    b64_data = str(b64_data).split(",")[1]
                                
                                if msg_type == "audio":
                                    audio_base64 = b64_data
                                    from utils.transcriber import transcribe_audio
                                    
                                    # 🎯 البحث عن مفتاح API يدعم Whisper (نفضل Groq لسرعته ومجانيته)
                                    # بغض النظر عن نموذج الباقة، نستخدم Groq لتحويل الصوت لنص مجاناً
                                    groq_model = await supabase.table("global_ai_models").select("api_key").eq("provider", "groq").limit(1).execute_async()
                                    transcribe_key = None
                                    
                                    if groq_model.data:
                                        transcribe_key = groq_model.data[0].get("api_key")
                                    else:
                                        # بديل: استخدام مفتاح OpenAI إذا لم يوجد Groq
                                        openai_model = await supabase.table("global_ai_models").select("api_key").eq("provider", "openai").limit(1).execute_async()
                                        if openai_model.data:
                                            transcribe_key = openai_model.data[0].get("api_key")
                                    
                                    if transcribe_key:
                                        import base64
                                        audio_bytes = base64.b64decode(b64_data)
                                        # محاولة التحويل الصوتي
                        if b64_data:
                            if "," in str(b64_data):
                                b64_data = str(b64_data).split(",")[1]
                            
                            if msg_type == "audio":
                                audio_base64 = b64_data
                                from utils.transcriber import transcribe_audio
                                
                                # 🎯 البحث عن مفتاح API يدعم Whisper (نفضل Groq لسرعته ومجانيته)
                                # بغض النظر عن نموذج الباقة، نستخدم Groq لتحويل الصوت لنص مجاناً
                                groq_model = await supabase.table("global_ai_models").select("api_key").eq("provider", "groq").limit(1).execute_async()
                                transcribe_key = None
                                
                                if groq_model.data:
                                    transcribe_key = groq_model.data[0].get("api_key")
                                else:
                                    # بديل: استخدام مفتاح OpenAI إذا لم يوجد Groq
                                    openai_model = await supabase.table("global_ai_models").select("api_key").eq("provider", "openai").limit(1).execute_async()
                                    if openai_model.data:
                                        transcribe_key = openai_model.data[0].get("api_key")
                                
                                if transcribe_key:
                                    import base64
                                    audio_bytes = base64.b64decode(b64_data)
                                    # محاولة التحويل الصوتي
                                    text = await transcribe_audio(audio_bytes, transcribe_key)
                                    if text:
                                        print(f"[VOICE] Transcribed Text via Whisper: {text}")
                                else:
                                    print("[VOICE ERROR] No Groq or OpenAI key found in global_ai_models for STT transcription.")
                            
                            elif msg_type == "image":
                                image_base64 = b64_data
                                if not text: text = "تحليل الصورة"
                    else:
                        print(f"[DEBUG] Media fetch failed: {media_res.status_code}")
            except Exception as ve:
                print(f"[MEDIA ERROR] Exception: {ve}")
        
        print(f"[DEBUG] Final Message text from {phone}: {text}")

        if not text and not audio_base64 and not image_base64:
            print("[DEBUG] Skipping message because text, audio, and image are all empty.")
            return
        
        if not phone:
            return

        cfg = await _find_client_by_instance(instance_name)
        if not cfg:
            print(f"[ERROR] No client found for instance: {instance_name}")
            return

        client_id   = cfg["client_id"]
        api_url     = cfg["evolution_api_url"]
        api_key     = cfg["evolution_api_key"]

        # التحقق من الصلاحية
        if not await _is_authorized(client_id, phone):
            print(f"[AUTH] Number {phone} is NOT authorized for client {client_id}")
            return

        # ⚡ تشغيل إشعار "جاري الكتابة" في الخلفية ليعمل أثناء تفكير الذكاء الاصطناعي
        try:
            import asyncio
            asyncio.create_task(_send_typing_indicator(api_url, api_key, instance_name, phone))
        except:
            pass

        # توليد الرد — ترتيب الوسائط: (client_id, phone_number, user_message, ...)
        print(f"[AI] Calling AI for client {client_id}, phone={phone}, text={text[:40]}...")
        ai_reply = await get_ai_response(
            client_id=client_id,
            phone_number=phone,
            user_message=text,
            image_base64=image_base64,
            audio_base64=audio_base64,
            message_id=msg_id,
            channel="whatsapp_evolution",
            base_url=base_url
        )

        # --- تفعيل الحفظ التلقائي للطلبات ---
        from merchant.reception.order_extractor import extract_order_json, build_order_record, validate_order_data, get_delivery_type_for_client
        
        order_data, ai_reply = extract_order_json(ai_reply)
        if order_data:
            try:
                # ✅ التحقق الصارم من اكتمال البيانات قبل الاعتماد
                delivery_type = get_delivery_type_for_client(client_id)
                is_valid, error_msg = validate_order_data(order_data, delivery_type)
                
                if not is_valid:
                    print(f"[AUTO-ORDER] REJECTED incomplete order: {error_msg}")
                    # لا نحفظ الطلب - الذكاء الاصطناعي سيتابع جمع البيانات
                else:
                    final_order = build_order_record(order_data, client_id, phone, "whatsapp", "AI")
                    res = await supabase.table("orders").insert(final_order).execute_async()
                    if res.data:
                        order_id = res.data[0]["id"]
                        invoice_url = f"{scheme}://{host}/invoice/{order_id}"
                        ai_reply += f"\n\n🧾 *رابط الفاتورة:*\n{invoice_url}"
                    print(f"[AUTO-ORDER] Order {final_order['order_number']} saved successfully for client {client_id}")
                    
                    # --- تحديث بيانات العميل في CRM ---
                    try:
                        from merchant.customers.customer_manager import update_customer_data, increment_order_count
                        clean_id = phone.split("@")[0].replace("+", "")
                        updates = {}
                        if order_data.get("customer_name"):
                            updates["customer_name"] = order_data["customer_name"]
                        if order_data.get("customer_address"):
                            updates["customer_address"] = order_data["customer_address"]
                        if order_data.get("customer_city"):
                            updates["customer_city"] = order_data["customer_city"]
                        if order_data.get("customer_phone"):
                            updates["phone_number"] = order_data["customer_phone"]
                        if updates:
                            update_customer_data(client_id, clean_id, updates)
                        increment_order_count(client_id, clean_id)
                    except Exception as crm_e:
                        print(f"[CRM ERROR] Failed to update customer: {crm_e}")
            except Exception as e:
                print(f"[AUTO-ORDER ERROR] Failed to save order: {e}")
        # ----------------------------------

        print(f"[AI] Reply: {ai_reply}")

        # اكتشاف الأزرار التفاعلية من رد الذكاء الاصطناعي
        from merchant.reception.buttons_handler import extract_buttons_from_reply, send_evolution_buttons
        clean_reply, buttons = extract_buttons_from_reply(ai_reply)

        # إرسال الرد
        if buttons:
            # محاولة إرسال أزرار تفاعلية
            status = await send_evolution_buttons(api_url, api_key, instance_name, phone, clean_reply, buttons)
            if not status:
                # Fallback: إرسال كنص عادي وتضمين الخيارات كقائمة مرقمة
                fallback_text = clean_reply + "\n\n"
                for idx, btn in enumerate(buttons):
                    fallback_text += f"*{idx + 1}-* {btn['text']}\n"
                status = await _send_evolution_message(api_url, api_key, instance_name, phone, fallback_text.strip())
        else:
            status = await _send_evolution_message(api_url, api_key, instance_name, phone, clean_reply)

        if status:
            print(f"[SUCCESS] Reply sent to {phone}")
        else:
            print(f"[ERROR] Evolution API rejected the reply to {phone}")

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[CRITICAL ERROR] Evolution webhook error: {e}")
    finally:
        # تنظيف الذاكرة بعد معالجة الرسالة (نجاح أو فشل)
        if msg_id:
            _processing_ids.discard(msg_id)
        if 'phone_lock' in locals():
            phone_lock.release()
