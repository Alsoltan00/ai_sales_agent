"""
merchant/reception/whatsapp_evolution_receiver.py
استقبال الرسائل من واتساب عبر Evolution API
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
    """إرسال رد عبر Evolution API"""
    # تنظيف الرقم من أي إضافات مثل @s.whatsapp.net
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
            if res.status_code >= 400:
                print(f"[EVOLUTION ERROR] Status: {res.status_code}, Body: {res.text}")
                return False
            return True
    except Exception as e:
        print(f"[SEND ERROR] Failed to call Evolution API: {e}")
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
        msg_content = data.get("message", {})
        
        # 1. جلب النص (إذا كانت رسالة نصية)
        text        = (
            msg_content.get("conversation") or
            msg_content.get("extendedTextMessage", {}).get("text") or
            ""
        )

        # 2. معالجة الرسائل الصوتية (إذا وجدت)
        if "audioMessage" in msg_content and not text:
            print(f"[DEBUG] Audio message detected from {phone}. Downloading...")
            cfg = _find_client_by_instance(instance_name)
            if cfg:
                from utils.transcriber import transcribe_audio
                from merchant.ai_training.ai_config import get_ai_config
                
                ai_cfg = get_ai_config(cfg["client_id"])
                ai_provider = ai_cfg.get("provider") if ai_cfg else "None"
                groq_key = ai_cfg.get("api_key") if ai_cfg and ai_provider == "groq" else None
                
                print(f"[DEBUG] AI Provider: {ai_provider}, Has Groq Key: {'Yes' if groq_key else 'No'}")

                if groq_key:
                    try:
                        # في نسخة v2 الحديثة، المسار غالباً يكون /instance/fetchMedia
                        fetch_url = f"{cfg['evolution_api_url'].rstrip('/')}/instance/fetchMedia"
                        media_payload = {"message": data}
                        headers = {"apikey": cfg["evolution_api_key"]}
                        
                        print(f"[DEBUG] Calling Evolution fetchMedia: {fetch_url}")
                        async with httpx.AsyncClient() as client:
                            media_res = await client.post(fetch_url, json=media_payload, headers=headers, timeout=20)
                            print(f"[DEBUG] Evolution Media Response Status: {media_res.status_code}")
                            
                            if media_res.status_code == 200:
                                media_data = media_res.json()
                                # تجربة عدة حقول محتملة للـ base64
                                b64_audio = media_data.get("base64") or media_data.get("data")
                                
                                if b64_audio:
                                    import base64
                                    # إذا كان النص يحتوي على بادئة مثل data:audio/ogg;base64,
                                    if "," in str(b64_audio):
                                        b64_audio = str(b64_audio).split(",")[1]
                                        
                                    audio_bytes = base64.b64decode(b64_audio)
                                    print(f"[DEBUG] Audio downloaded ({len(audio_bytes)} bytes). Transcribing...")
                                    text = await transcribe_audio(audio_bytes, groq_key)
                                    print(f"[VOICE] Transcribed Text: {text}")
                                else:
                                    print("[DEBUG] No base64 data found in media response")
                            else:
                                print(f"[DEBUG] Media fetch failed: {media_res.text}")
                    except Exception as ve:
                        print(f"[VOICE ERROR] Exception during audio processing: {ve}")
                else:
                    print("[DEBUG] Skipping audio because Groq is not the active provider or Key is missing")
        
        print(f"[DEBUG] Final Message text from {phone}: {text}")

        if not text or not phone:
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
        ai_reply = await get_ai_response(client_id, text, phone, channel="whatsapp_evolution")
        print(f"[AI] Reply: {ai_reply}")

        # إرسال الرد
        status = await _send_evolution_message(api_url, api_key, instance_name, phone, ai_reply)
        if status:
            print(f"[SUCCESS] Message sent to {phone}")
        else:
            print(f"[ERROR] Evolution API rejected the message to {phone}")

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[CRITICAL ERROR] Evolution webhook error: {e}")

    return Response(status_code=200)
