import os
import json
import httpx
from database.db_client import get_supabase_client

async def get_ai_response(client_id: str, user_message: str, phone_number: str) -> str:
    """
    ظٹط¬ظ„ط¨ ط¥ط¹ط¯ط§ط¯ط§طھ ط§ظ„ط°ظƒط§ط، ط§ظ„ط§طµط·ظ†ط§ط¹ظٹ ظˆط§ظ„ط¨ظٹط§ظ†ط§طھ ط«ظ… ظٹظˆظ„ط¯ ط±ط¯ط§ظ‹ ط§ط­طھط±ط§ظپظٹط§ظ‹
    """
    supabase = get_supabase_client()

    # 1. ط¬ظ„ط¨ ط¥ط¹ط¯ط§ط¯ط§طھ ط§ظ„ظˆظƒظٹظ„
    client_data = supabase.table("clients").select(
        "company_name, ai_agent_name, ai_tone, business_description"
    ).eq("id", client_id).single().execute()

    # 2. ط¬ظ„ط¨ ط¥ط¹ط¯ط§ط¯ط§طھ ط§ظ„ظ†ظ…ظˆط°ط¬
    ai_cfg = supabase.table("ai_models_config").select(
        "model_id, api_key, provider"
    ).eq("client_id", client_id).single().execute()

    if not ai_cfg.data:
        return "ط¹ط°ط±ط§ظ‹طŒ ظ„ظ… ظٹطھظ… ط¥ط¹ط¯ط§ط¯ ط§ظ„ط°ظƒط§ط، ط§ظ„ط§طµط·ظ†ط§ط¹ظٹ ط¨ط¹ط¯. ظٹط±ط¬ظ‰ ط§ظ„طھظˆط§طµظ„ ظ…ط¹ ط§ظ„ط¯ط¹ظ…."

    model_id  = ai_cfg.data["model_id"]
    api_key   = ai_cfg.data["api_key"]
    provider  = ai_cfg.data.get("provider", "openai")

    c         = client_data.data or {}
    agent_name   = c.get("ai_agent_name") or c.get("company_name") or "ط§ظ„ظ…ط³ط§ط¹ط¯"
    tone         = c.get("ai_tone") or "ط§ط­طھط±ط§ظپظٹ ظˆظ…ظ‡ط°ط¨"
    description  = c.get("business_description") or ""

    # 3. جلب بيانات المتجر للسياق
    store_data = ""
    try:
        sync_cfg = supabase.table("sync_config").select("*").eq("client_id", client_id).single().execute()
        if sync_cfg.data and sync_cfg.data.get("source_type") == "aiven":
            # يمكن إضافة منطق جلب من MySQL هنا لاحقاً
            pass
        elif sync_cfg.data and sync_cfg.data.get("source_type") == "google_sheets":
            # يمكن إضافة منطق جلب من جوجل شيتس هنا لاحقاً
            pass
        elif sync_cfg.data and sync_cfg.data.get("source_type") == "excel":
            # جلب البيانات اليدوية المرفوعة
            manual_res = supabase.table("merchant_manual_data").select("data").eq("client_id", client_id).execute()
            if manual_res.data:
                # نأخذ أول سجل (بما أن الربط 1-1)
                store_data = json.dumps(manual_res.data[0]["data"], ensure_ascii=False)

    except Exception as e:
        print(f"Warning: Could not fetch store data: {e}")

    # 4. ط¨ظ†ط§ط، System Prompt
    system_prompt = f"""ط£ظ†طھ {agent_name}طŒ ظ…ظ†ط¯ظˆط¨ ظ…ط¨ظٹط¹ط§طھ ط°ظƒظٹ ظٹط¹ظ…ظ„ ظ„ط¯ظ‰ {c.get('company_name', 'ط§ظ„ط´ط±ظƒط©')}.

ظ„ظ‡ط¬ط© ط§ظ„ط±ط¯: {tone}

ظ…ط¹ظ„ظˆظ…ط§طھ ط§ظ„ط´ط±ظƒط© ظˆط§ظ„ط®ط¯ظ…ط§طھ:
{description}

{f"ط¨ظٹط§ظ†ط§طھ ط§ظ„ظ…ظ†طھط¬ط§طھ ظˆط§ظ„ظ…ط®ط²ظˆظ† ط§ظ„ط­ط§ظ„ظٹ (JSON):{chr(10)}{store_data}" if store_data else ""}

ظ‚ظˆط§ط¹ط¯ ظ…ظ‡ظ…ط©:
- ط±ط¯ ط¯ط§ط¦ظ…ط§ظ‹ ط¨ط§ظ„ط¹ط±ط¨ظٹط© ظ…ط§ ظ„ظ… ظٹطھط­ط¯ط« ط§ظ„ط¹ظ…ظٹظ„ ط¨ظ„ط؛ط© ط£ط®ط±ظ‰
- ظƒظ† ظ…ظ‚ظ†ط¹ط§ظ‹ ظˆظ…ط­طھط±ظ…ط§ظ‹ ظˆظ…ط±ظƒط²ط§ظ‹ ط¹ظ„ظ‰ ط¥طھظ…ط§ظ… ط§ظ„ط¨ظٹط¹
- ط¥ط°ط§ ط³ظڈط¦ظ„طھ ط¹ظ† ط³ط¹ط± ط؛ظٹط± ظ…ظˆط¬ظˆط¯ ظپظٹ ط§ظ„ط¨ظٹط§ظ†ط§طھطŒ ظ‚ظ„ ط£ظ†ظƒ ط³طھطھط­ظ‚ظ‚ ظˆطھط¹ظˆط¯ ظ„ظ„ط¹ظ…ظٹظ„
- ظ„ط§ طھط°ظƒط± ط£ظ†ظƒ ط°ظƒط§ط، ط§طµط·ظ†ط§ط¹ظٹ ط¥ظ„ط§ ط¥ط°ط§ ط³ظڈط¦ظ„طھ ظ…ط¨ط§ط´ط±ط©
- ط§ظ„ط±ط¯ظˆط¯ طھظƒظˆظ† ظ…ط®طھطµط±ط© ظˆظˆط§ط¶ط­ط© (ط­ط¯ ط£ظ‚طµظ‰ 3 ظپظ‚ط±ط§طھ ظ‚طµظٹط±ط©)
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_message}
    ]

    # 5. ط§ط³طھط¯ط¹ط§ط، API ط­ط³ط¨ ط§ظ„ظ…ط²ظˆط¯
    try:
        if provider == "openai":
            response = await _call_openai(api_key, model_id, messages)
        elif provider == "anthropic":
            response = await _call_anthropic(api_key, model_id, messages, system_prompt)
        elif provider == "groq":
            response = await _call_groq(api_key, model_id, messages)
        else:
            response = await _call_openai(api_key, model_id, messages)

        # 6. طھط³ط¬ظٹظ„ ط§ظ„ط³ط¬ظ„
        _log_message(supabase, client_id, user_message, response, phone_number)
        return response

    except Exception as e:
        print(f"AI call error: {e}")
        return "ط¹ط°ط±ط§ظ‹طŒ ط­ط¯ط« ط®ط·ط£ ط£ط«ظ†ط§ط، ظ…ط¹ط§ظ„ط¬ط© ط·ظ„ط¨ظƒ. ظٹط±ط¬ظ‰ ط§ظ„ظ…ط­ط§ظˆظ„ط© ظ…ط±ط© ط£ط®ط±ظ‰."


async def _call_openai(api_key: str, model_id: str, messages: list) -> str:
    async with httpx.AsyncClient() as client:
        res = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model_id, "messages": messages, "max_tokens": 500},
            timeout=30
        )
        data = res.json()
        return data["choices"][0]["message"]["content"].strip()


async def _call_anthropic(api_key: str, model_id: str, messages: list, system: str) -> str:
    # Anthropic requires system as a top-level field
    user_messages = [m for m in messages if m["role"] != "system"]
    async with httpx.AsyncClient() as client:
        res = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json"
            },
            json={"model": model_id, "system": system, "messages": user_messages, "max_tokens": 500},
            timeout=30
        )
        data = res.json()
        return data["content"][0]["text"].strip()


async def _call_groq(api_key: str, model_id: str, messages: list) -> str:
    async with httpx.AsyncClient() as client:
        res = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model_id, "messages": messages, "max_tokens": 500},
            timeout=30
        )
        data = res.json()
        return data["choices"][0]["message"]["content"].strip()


def _log_message(supabase, client_id: str, user_message: str, ai_response: str, phone_number: str):
    try:
        supabase.table("message_logs").insert({
            "client_id": client_id,
            "channel": "unknown",
            "direction": "in",
            "phone_number": phone_number,
            "message_text": user_message,
            "ai_response": ai_response
        }).execute()
    except Exception as e:
        print(f"Log error: {e}")
