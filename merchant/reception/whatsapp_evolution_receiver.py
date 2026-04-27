"""
merchant/reception/whatsapp_evolution_receiver.py
استقبال الرسائل من واتساب عبر Evolution API
"""
import httpx
from fastapi import APIRouter, Request, Response
from database.db_client import get_supabase_client
from merchant.ai_engine import get_ai_response

router = APIRouter(prefix="/webhook", tags=["WhatsApp Evolution Webhook"])


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
        client = supabase.table("clients").select("allow_all_numbers").eq("id", client_id).single().execute()
        if client.data and client.data.get("allow_all_numbers"):
            return True
        # Normalize phone: remove @s.whatsapp.net suffix if present
        clean_phone = phone.replace("@s.whatsapp.net", "").replace("@c.us", "")
        res = supabase.table("authorized_numbers").select("id").eq("client_id", client_id).eq("phone_number", clean_phone).execute()
        return bool(res.data)
    except Exception:
        return False


async def _send_evolution_message(api_url: str, api_key: str, instance_name: str, phone: str, text: str):
    """ط¥ط±ط³ط§ظ„ ط±ط¯ ط¹ط¨ط± Evolution API"""
    # Clean phone number
    clean_phone = phone.replace("@s.whatsapp.net", "").replace("@c.us", "")
    url = f"{api_url.rstrip('/')}/message/sendText/{instance_name}"
    headers = {"apikey": api_key, "Content-Type": "application/json"}
    payload = {
        "number": clean_phone,
        "options": {"delay": 1200, "presence": "composing"},
        "textMessage": {"text": text}
    }
    async with httpx.AsyncClient() as client:
        await client.post(url, headers=headers, json=payload, timeout=15)


@router.post("/whatsapp/evolution/{instance_name}")
async def evolution_webhook(instance_name: str, request: Request):
    """Webhook ظ„ط§ط³طھظ‚ط¨ط§ظ„ ط±ط³ط§ط¦ظ„ ظˆط§طھط³ط§ط¨ ط¹ط¨ط± Evolution API"""
    try:
        body = await request.json()

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
        text        = (
            msg_content.get("conversation") or
            msg_content.get("extendedTextMessage", {}).get("text") or
            ""
        )

        if not text or not phone:
            return Response(status_code=200)

        # البحث عن التاجر
        cfg = _find_client_by_instance(instance_name)
        if not cfg:
            return Response(status_code=200)

        client_id   = cfg["client_id"]
        api_url     = cfg["evolution_api_url"]
        api_key     = cfg["evolution_api_key"]

        # التحقق من الصلاحية
        if not _is_authorized(client_id, phone):
            return Response(status_code=200)

        # توليد الرد
        ai_reply = await get_ai_response(client_id, text, phone)

        # إرسال الرد
        await _send_evolution_message(api_url, api_key, instance_name, phone, ai_reply)

    except Exception as e:
        print(f"Evolution webhook error: {e}")

    return Response(status_code=200)
