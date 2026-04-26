"""
merchant/reception/telegram_receiver.py
ط§ط³طھظ‚ط¨ط§ظ„ ط§ظ„ط±ط³ط§ط¦ظ„ ظ…ظ† طھظٹظ„ظٹط¬ط±ط§ظ… ط¹ط¨ط± Webhook
"""
import json
import httpx
from fastapi import APIRouter, Request, Response
from database.db_client import get_supabase_client
from merchant.ai_engine import get_ai_response

router = APIRouter(prefix="/webhook", tags=["Telegram Webhook"])


def _find_client_by_token(bot_token: str) -> dict | None:
    """ط§ظ„ط¨ط­ط« ط¹ظ† ط§ظ„طھط§ط¬ط± ط¨ظˆط§ط³ط·ط© ط±ظ…ط² ط§ظ„ط¨ظˆطھ"""
    supabase = get_supabase_client()
    try:
        res = supabase.table("channels_config").select("client_id").eq("telegram_bot_token", bot_token).single().execute()
        return res.data
    except Exception:
        return None


def _is_authorized(client_id: str, phone: str) -> bool:
    """ط§ظ„طھط­ظ‚ظ‚ ظ…ظ† طµظ„ط§ط­ظٹط© ط§ظ„ط±ظ‚ظ…"""
    supabase = get_supabase_client()
    try:
        client = supabase.table("clients").select("allow_all_numbers").eq("id", client_id).single().execute()
        if client.data and client.data.get("allow_all_numbers"):
            return True
        res = supabase.table("authorized_numbers").select("id").eq("client_id", client_id).eq("phone_number", str(phone)).execute()
        return bool(res.data)
    except Exception:
        return False


async def _send_telegram_message(bot_token: str, chat_id: int, text: str):
    """ط¥ط±ط³ط§ظ„ ط±ط¯ ط¹ط¨ط± طھظٹظ„ظٹط¬ط±ط§ظ…"""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    async with httpx.AsyncClient() as client:
        await client.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)


@router.post("/telegram/{bot_token}")
async def telegram_webhook(bot_token: str, request: Request):
    """Webhook ظ„ط§ط³طھظ‚ط¨ط§ظ„ ط±ط³ط§ط¦ظ„ طھظٹظ„ظٹط¬ط±ط§ظ…"""
    try:
        body = await request.json()
        message = body.get("message", {})
        if not message:
            return Response(status_code=200)

        chat_id     = message["chat"]["id"]
        text        = message.get("text", "")
        from_user   = message.get("from", {})
        phone_str   = str(chat_id)  # طھظٹظ„ظٹط¬ط±ط§ظ… ظٹط³طھط®ط¯ظ… chat_id ظƒظ…ط¹ط±ظپ

        if not text:
            return Response(status_code=200)

        # ط§ظ„ط¨ط­ط« ط¹ظ† ط§ظ„طھط§ط¬ط±
        client_cfg = _find_client_by_token(bot_token)
        if not client_cfg:
            return Response(status_code=200)

        client_id = client_cfg["client_id"]

        # ط§ظ„طھط­ظ‚ظ‚ ظ…ظ† ط§ظ„طµظ„ط§ط­ظٹط©
        if not _is_authorized(client_id, phone_str):
            return Response(status_code=200)

        # طھظˆظ„ظٹط¯ ط§ظ„ط±ط¯
        ai_reply = await get_ai_response(client_id, text, phone_str)

        # ط¥ط±ط³ط§ظ„ ط§ظ„ط±ط¯
        await _send_telegram_message(bot_token, chat_id, ai_reply)

    except Exception as e:
        print(f"Telegram webhook error: {e}")

    return Response(status_code=200)
