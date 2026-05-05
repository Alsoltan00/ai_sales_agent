import os
import json
import httpx
from database.db_client import get_supabase_client

def _normalize_col_name(name: str) -> str:
    if not isinstance(name, str):
        return ""
    return " ".join(name.strip().lower().split())

async def get_ai_response(client_id: str, phone_number: str, user_message: str, 
                         image_base64: str = None, audio_base64: str = None, 
                         message_id: str = None, channel: str = "whatsapp"):
    """
    Main orchestrator for AI logic. Fetches context, builds prompt, and calls LLM.
    """
    supabase = get_supabase_client()
    
    # 1. Fetch client/merchant settings
    client_res = supabase.table("clients").select("*").eq("id", client_id).single().execute()
    if not client_res.data:
        return "عذراً، لم يتم العثور على إعدادات هذا المتجر."
    
    client = client_res.data
    api_key = client.get("api_key")
    model_id = client.get("model_id", "gpt-3.5-turbo")
    provider = client.get("ai_provider", "openai")
    agent_name = client.get("agent_name", "نوره")
    company_name = client.get("company_name", "متجرنا")
    store_activity = client.get("store_activity", "تجارة عامة")
    description = client.get("description", "")
    tone = client.get("ai_tone", "friendly")
    messages_used = client.get("messages_used", 0)
    message_limit = client.get("message_limit", 1000)

    if messages_used >= message_limit:
        return "نعتذر منك، لقد انتهى الرصيد المخصص للرسائل لهذا المتجر حالياً."

    # 2. Fetch Merchant Data
    store_data = ""
    try:
        data_res = supabase.table("merchant_manual_data").select("data").eq("client_id", client_id).execute()
        if data_res.data:
            rows = data_res.data[0].get("data", [])
            if rows:
                formatted_lines = []
                for item in rows:
                    line = " | ".join([f"{k}: {v}" for k, v in item.items()])
                    formatted_lines.append(f"- {line}")
                store_data = "\n".join(formatted_lines)
    except Exception as e:
        print(f"Warning: Could not fetch store data: {e}")

    # 3. Column Training
    column_training_prompt = ""
    try:
        col_res = supabase.table("column_training").select("column_name, column_note").eq("client_id", client_id).execute()
        if col_res.data:
            notes = [f"- {c['column_name']}: {c['column_note']}" for c in col_res.data]
            column_training_prompt = "تعليمات خاصة بأعمدة البيانات:\n" + "\n".join(notes)
    except Exception as e:
        print(f"Warning: Could not fetch column training: {e}")

    # 4. Business Rules
    business_rules_prompt = ""
    try:
        rules_res = supabase.table("business_rules").select("rules_data").eq("client_id", client_id).single().execute()
        if rules_res.data and rules_res.data.get("rules_data"):
            rd = rules_res.data["rules_data"]
            checkout = rd.get('checkout_type', 'store')
            if checkout == 'chat':
                checkout_instructions = "مسار إتمام الطلب: داخل المحادثة (واتساب). يجب عليك أخذ بيانات العميل (الاسم، الجوال، العنوان) وتأكيد الطلب بالكامل."
                pm = []
                if rd.get('chat_payment_cod'): pm.append("الدفع عند الاستلام")
                if rd.get('chat_payment_transfer'): pm.append(f"تحويل بنكي ({rd.get('bank_accounts', '')})")
                if rd.get('chat_payment_link'): pm.append(f"رابط دفع ({rd.get('payment_links', '')})")
                checkout_instructions += f"\n- طرق الدفع المتاحة: {', '.join(pm) if pm else 'حسب الاتفاق'}."
            else:
                checkout_instructions = "مسار إتمام الطلب: عبر المتجر الإلكتروني. وجه العميل لرابط المنتج في المتجر."

            business_rules_prompt = f"""
دستور عمل وقواعد العمل (يجب الالتزام بها قطعيًا):
- {checkout_instructions}
- سياسة الخصم: {rd.get('discount_type', 'حسب السياسة')}. {rd.get('discount_msg', '')}
- نبرة الصوت: {rd.get('tone_type', tone)}. {rd.get('complaint_msg', '')}
"""
    except Exception as e:
        print(f"Warning: Could not fetch business rules: {e}")

    # 5. Build Product Context
    product_context = ""
    if store_data:
        product_context = f"""
بيانات المنتجات والمخزون المتاحة حالياً:
-------------------------------------------
{store_data}
-------------------------------------------
{column_training_prompt}
ملاحظة هامة جداً للذكاء الاصطناعي: 
- إذا قال العميل "الأول" أو "أعطني هذا" أو أي إشارة لمنتج، فيجب عليك تجاهل القائمة أعلاه تماماً والبحث في رسالتك السابقة فوراً لتعرف ما هو المنتج المقصود.
"""

    system_prompt = f"""هويتك: أنت "{agent_name}" من "{company_name}". 
- وظيفتك بيع منتجات [{store_activity}].
- تحدث بلهجة العميل وكن مختصراً.
- لا تكرر التعريف بنفسك إذا كان هناك سابق محادثة.

{product_context}
{business_rules_prompt}
"""

    # 6. Fetch REAL Chat History
    chat_history_messages = []
    try:
        history_res = supabase.table("message_logs") \
            .select("message_text, ai_response, timestamp") \
            .order("timestamp", desc=True) \
            .eq("client_id", client_id) \
            .eq("phone_number", phone_number) \
            .limit(10) \
            .execute()
        
        if history_res.data:
            sorted_history = sorted(history_res.data, key=lambda x: x.get("timestamp", ""))
            for msg in sorted_history:
                u = (msg.get("message_text") or "").strip()
                a = (msg.get("ai_response") or "").strip()
                if u: chat_history_messages.append({"role": "user", "content": u})
                if a: chat_history_messages.append({"role": "assistant", "content": a})
    except Exception as e:
        print(f"Warning: History fetch error: {e}")

    # 7. Construct final messages
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(chat_history_messages[-8:])

    if image_base64:
        content = [{"type": "text", "text": user_message or "حلل الصورة"}]
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}})
        messages.append({"role": "user", "content": content})
    else:
        messages.append({"role": "user", "content": user_message})

    # 8. Call LLM
    try:
        if not api_key:
            raise Exception(f"مفتاح الـ API الخاص بـ {provider} غير موجود في الإعدادات.")

        if provider == "openai":
            response = await _call_openai(api_key, model_id, messages)
        elif provider == "google":
            response = await _call_google(api_key, model_id, messages, system_prompt)
        elif provider == "groq":
            response = await _call_groq(api_key, model_id, messages)
        elif provider == "anthropic":
            response = await _call_anthropic(api_key, model_id, messages, system_prompt)
        elif provider == "openrouter":
            response = await _call_openrouter(api_key, model_id, messages)
        else:
            # Fallback to OpenRouter as it's the user's primary choice
            response = await _call_openrouter(api_key, model_id, messages)

        _log_message(supabase, client_id, user_message, response, phone_number, channel, message_id)
        supabase.table("clients").update({"messages_used": messages_used + 1}).eq("id", client_id).execute()
        return response
    except Exception as e:
        print(f"AI Error for client {client_id}: {e}")
        return f"عذراً، {str(e)[:100]}"

async def _call_anthropic(api_key: str, model_id: str, messages: list, system: str) -> str:
    user_messages = [m for m in messages if m["role"] != "system"]
    async with httpx.AsyncClient() as client:
        res = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json"
            },
            json={"model": model_id, "system": system, "messages": user_messages, "max_tokens": 500, "temperature": 0.1},
            timeout=30
        )
        data = res.json()
        if "content" not in data:
            raise Exception(f"Anthropic: {data.get('error', {}).get('message', 'Unknown')}")
        return data["content"][0]["text"].strip()

async def _call_openai(api_key: str, model_id: str, messages: list) -> str:
    async with httpx.AsyncClient() as client:
        res = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model_id, "messages": messages, "max_tokens": 500, "temperature": 0.1},
            timeout=30
        )
        data = res.json()
        if "choices" not in data:
            raise Exception(f"OpenAI: {data.get('error', {}).get('message', 'Unknown')}")
        return data["choices"][0]["message"]["content"].strip()

async def _call_groq(api_key: str, model_id: str, messages: list) -> str:
    async with httpx.AsyncClient() as client:
        res = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model_id, "messages": messages, "max_tokens": 500, "temperature": 0.1},
            timeout=30
        )
        data = res.json()
        if "choices" not in data:
            raise Exception(f"Groq: {data.get('error', {}).get('message', 'Unknown')}")
        return data["choices"][0]["message"]["content"].strip()

async def _call_google(api_key: str, model_id: str, messages: list, system: str) -> str:
    # Normalize model_id
    m_id = model_id.strip()
    if not m_id.startswith("models/"):
        m_id = f"models/{m_id}"
        
    url = f"https://generativelanguage.googleapis.com/v1beta/{m_id}:generateContent?key={api_key}"
    contents = []
    for msg in messages:
        if msg["role"] == "system": continue
        role = "user" if msg["role"] == "user" else "model"
        parts = []
        if isinstance(msg["content"], str):
            parts.append({"text": msg["content"]})
        elif isinstance(msg["content"], list):
            for part in msg["content"]:
                if part["type"] == "text": parts.append({"text": part["text"]})
                elif part["type"] == "image_url":
                    b64 = part["image_url"]["url"].split(",")[-1]
                    parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})
        contents.append({"role": role, "parts": parts})
    
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": contents,
        "generationConfig": {"maxOutputTokens": 500, "temperature": 0.1}
    }
    async with httpx.AsyncClient() as client:
        res = await client.post(url, json=body, timeout=30)
        data = res.json()
        if res.status_code != 200:
            err = data.get("error", {}).get("message", "Unknown Google Error")
            raise Exception(f"Google: {err}")
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception:
            raise Exception("Google: Unexpected format")

async def _call_openrouter(api_key: str, model_id: str, messages: list) -> str:
    async with httpx.AsyncClient() as client:
        res = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model_id, "messages": messages},
            timeout=30
        )
        data = res.json()
        return data["choices"][0]["message"]["content"].strip()

def _log_message(supabase, client_id: str, user_message: str, ai_response: str, phone_number: str, channel: str = "whatsapp", message_id: str = None):
    try:
        supabase.table("message_logs").insert({
            "client_id": client_id,
            "channel": channel,
            "direction": "in",
            "phone_number": phone_number,
            "message_text": user_message,
            "ai_response": ai_response,
            "message_id": message_id
        }).execute()
    except Exception as e:
        print(f"Log error: {e}")