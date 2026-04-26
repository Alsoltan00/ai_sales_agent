"""
merchant/reception/whatsapp_official_receiver.py
ط§ط³طھظ‚ط¨ط§ظ„ ط§ظ„ط±ط³ط§ط¦ظ„ ط¹ط¨ط± WhatsApp Cloud API ط§ظ„ط±ط³ظ…ظٹ ظ…ظ† Meta
"""
import httpx
from fastapi import APIRouter, Request, Response, Query
from database.db_client import get_supabase_client
from merchant.ai_engine import get_ai_response

router = APIRouter(prefix="/webhook", tags=["WhatsApp Official Webhook"])


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


@router.get("/whatsapp/official")
async def verify_official_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify.token")
):
    """ط§ظ„طھط­ظ‚ظ‚ ظ…ظ† Webhook ط¹ظ†ط¯ ط±ط¨ط·ظ‡ ظ…ط¹ Meta"""
    supabase = get_supabase_client()
    try:
        # ط§ظ„ط¨ط­ط« ط¹ظ† طھط§ط¬ط± ظٹظ…ظ„ظƒ ظ‡ط°ط§ ط§ظ„ظ€ verify_token
        res = supabase.table("channels_config").select("meta_verify_token").execute()
        valid_tokens = [row["meta_verify_token"] for row in (res.data or []) if row.get("meta_verify_token")]

        if hub_mode == "subscribe" and hub_verify_token in valid_tokens:
            return Response(content=hub_challenge, status_code=200)
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
                    if msg.get("type") != "text":
                        continue

                    from_phone = msg.get("from", "")
                    text       = msg.get("text", {}).get("body", "")

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

                    # طھظˆظ„ظٹط¯ ط§ظ„ط±ط¯
                    ai_reply = await get_ai_response(client_id, text, from_phone)

                    # ط¥ط±ط³ط§ظ„ ط§ظ„ط±ط¯
                    await _send_official_message(access_token, phone_number_id, from_phone, ai_reply)

    except Exception as e:
        print(f"Official WhatsApp webhook error: {e}")

    return Response(status_code=200)
