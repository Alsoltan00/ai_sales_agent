"""
merchant/reception/whatsapp_evolution_receiver.py
استقبال الرسائل من واتساب عبر Evolution API - تحديث روابط v2
"""
import httpx
from fastapi import APIRouter, Request, Response
from database.db_client import get_supabase_client
from merchant.ai_engine import get_ai_response

router = APIRouter(tags=["WhatsApp Evolution Webhook"])


def _find_client_by_instance(instance_name: str) -> dict | None:
    supabase = get_supabase_client()
    try:
        res = supabase.table("channels_config").select("*").eq("evolution_instance_name", instance_name).single().execute()
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
            print(f"[AUTH] Ignoring GROUP message from {phone}")
            return False

        # 2. If allow_all is ON, ALLOW (both private and groups if not ignored)
        if allow_all:
            return True

        # 3. Check authorized numbers list (for private messages or groups if allow_all is off)
        # Normalize phone: remove suffix
        clean_phone = phone.replace("@s.whatsapp.net", "").replace("@c.us", "").replace("@g.us", "")
        res = supabase.table("authorized_numbers").select("id").eq("client_id", client_id).eq("phone_number", clean_phone).execute()
        return bool(res.data)
    except Exception as e:
        print(f"[AUTH ERROR] {e}")
        return False


async def _send_evolution_message(api_url: str, api_key: str, instance_name: str, phone: str, text: str) -> bool:
    """إرسال رد نصي عبر Evolution API"""
    clean_number = phone.split("@")[0]
    url = f"{api_url.rstrip('/')}/message/sendText/{instance_name}"
    headers = {"apikey": api_key, "Content-Type": "application/json"}
    payload = {
        "number": clean_number,
        "text": text,
        "options": {"delay": 1200, "presence": "composing", "linkPreview": False}
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


@router.post("/whatsapp/evolution/{instance_name}")
async def evolution_webhook(instance_name: str, request: Request):
    """Webhook لاستقبال رسائل واتساب عبر Evolution API"""
    try:
        body = await request.json()
        print(f"[DEBUG] Received Webhook for instance: {instance_name}")

        # Evolution API sends different event types
        event = body.get("event", "")
        if event not in ("messages.upsert", "MESSAGES_UPSERT"):
            return Response(status_code=200)

        data = body.get("data", {})
        key  = data.get("key", {})

        # تجاهل الرسائل الصادرة من الجهاز نفسه
        if key.get("fromMe", False):
            return Response(status_code=200)

        phone       = key.get("remoteJid", "")
        msg_id      = key.get("id")
        msg_content = data.get("message", {})

        # 1. منع تكرار الرد على نفس الرسالة (Deduplication)
        if msg_id:
            try:
                supabase = get_supabase_client()
                check_dup = supabase.table("message_logs").select("id").eq("message_id", msg_id).execute()
                if check_dup.data and len(check_dup.data) > 0:
                    print(f"[DEBUG] Skipping duplicate message: {msg_id}")
                    return Response(status_code=200)
            except Exception as dup_err:
                print(f"[DEBUG] Deduplication check failed (maybe column missing?): {dup_err}")
                # نفضل الرد حتى لو فشل التحقق من التكرار
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
        else:
            # للرسائل غير النصية، نأخذ الوصف (Caption) فقط إذا وجد
            text = msg_content.get("imageMessage", {}).get("caption") or \
                   msg_content.get("videoMessage", {}).get("caption") or ""

        # 2. معالجة الرسائل الصوتية والصور
        image_base64 = None
        audio_base64 = None
        if msg_type in ("audio", "image"):
            print(f"[DEBUG] {msg_type.capitalize()} message detected from {phone}. Downloading...")
            cfg = _find_client_by_instance(instance_name)
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
                                    # محاولة جلب المفتاح للتحويل الصوتي
                                    model_res = supabase.table("clients").select("subscription_plan").eq("id", cfg["client_id"]).single().execute()
                                    if model_res.data:
                                        plan = model_res.data.get("subscription_plan")
                                        plan_res = supabase.table("subscription_plans").select("permissions").eq("name", plan).single().execute()
                                        if plan_res.data:
                                            import json
                                            perms = plan_res.data.get("permissions", {})
                                            if isinstance(perms, str): perms = json.loads(perms)
                                            mid = perms.get("assigned_model_id")
                                            if mid:
                                                ai_m = supabase.table("global_ai_models").select("*").eq("id", mid).single().execute()
                                                if ai_m.data:
                                                    api_key = ai_m.data.get("api_key")
                                                    provider = ai_m.data.get("provider")
                                                    
                                                    # لا نحتاج لتحويل الصوت لنص إذا كان المحرك هو Gemini (Google) لأنه يدعم الصوت مباشرة
                                                    if provider != "google":
                                                        import base64
                                                        audio_bytes = base64.b64decode(b64_data)
                                                        # محاولة التحويل الصوتي (فقط لـ Groq/OpenAI)
                                                        text = await transcribe_audio(audio_bytes, api_key)
                                                        if text:
                                                            print(f"[VOICE] Transcribed Text: {text}")
                                                    else:
                                                        print("[DEBUG] Skipping transcription for Google provider, using native audio support.")
                                
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
            return Response(status_code=200)
        
        if not phone:
            return Response(status_code=200)

        # البحث عن التاجر (إذا لم يتم البحث عنه سابقاً)
        cfg = _find_client_by_instance(instance_name)
        if not cfg:
            print(f"[ERROR] No client found for instance: {instance_name}")
            return Response(status_code=200)

        client_id   = cfg["client_id"]
        api_url     = cfg["evolution_api_url"]
        api_key     = cfg["evolution_api_key"]

        # التحقق من الصلاحية
        if not _is_authorized(client_id, phone):
            print(f"[AUTH] Number {phone} is NOT authorized for client {client_id}")
            return Response(status_code=200)

        # توليد الرد
        print(f"[AI] Calling AI for client {client_id}...")
        ai_reply = await get_ai_response(client_id, text, phone, channel="whatsapp_evolution", image_base64=image_base64, audio_base64=audio_base64, message_id=msg_id)
        print(f"[AI] Reply: {ai_reply}")

        # إرسال الرد
        if msg_type == "audio":
            from utils.tts import text_to_speech_b64
            audio_b64 = await text_to_speech_b64(ai_reply)
            if audio_b64:
                status = await _send_evolution_audio(api_url, api_key, instance_name, phone, audio_b64)
            else:
                status = await _send_evolution_message(api_url, api_key, instance_name, phone, ai_reply)
        else:
            status = await _send_evolution_message(api_url, api_key, instance_name, phone, ai_reply)

        if status:
            print(f"[SUCCESS] Reply sent to {phone}")
        else:
            print(f"[ERROR] Evolution API rejected the reply to {phone}")

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[CRITICAL ERROR] Evolution webhook error: {e}")

    return Response(status_code=200)
