import os
import json
import httpx
from database.db_client import get_supabase_client

async def get_ai_response(client_id: str, user_message: str, phone_number: str, channel: str = "unknown") -> str:
    """
    يجلب إعدادات الذكاء الاصطناعي والبيانات ثم يولد رداً احترافياً
    """
    supabase = get_supabase_client()

    # 1. جلب إعدادات الوكيل (الاسم والشركة من جدولين مختلفين)
    try:
        # جلب اسم الشركة
        client_res = supabase.table("clients").select("company_name").eq("id", client_id).single().execute()
        company_name = client_res.data.get("company_name", "الشركة") if client_res.data else "الشركة"

        # جلب إعدادات التخطيط (الشخصية)
        planning_res = supabase.table("planning_config").select(
            "sales_agent_name, dialect_instructions, company_description"
        ).eq("client_id", client_id).single().execute()
        
        p = planning_res.data or {}
        agent_name  = p.get("sales_agent_name") or company_name
        tone        = p.get("dialect_instructions") or "احترافي ومهذب"
        description = p.get("company_description") or ""
    except Exception as e:
        print(f"Error fetching planning config: {e}")
        company_name = "الشركة"
        agent_name = "المساعد"
        tone = "احترافي"
        description = ""

    # 2. جلب إعدادات النموذج النشط
    try:
        ai_cfg = supabase.table("ai_models_config").select(
            "model_id, api_key, provider"
        ).eq("client_id", client_id).eq("is_active", True).execute()
        ai_cfg_data = ai_cfg.data[0] if ai_cfg.data else None
    except:
        ai_cfg_data = None

    if not ai_cfg_data:
        return "عذراً، لم يتم إعداد الذكاء الاصطناعي بعد. يرجى التواصل مع الدعم."

    model_id  = ai_cfg_data["model_id"]
    api_key   = ai_cfg_data["api_key"]
    provider  = ai_cfg_data.get("provider", "openai")

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

    # 4. بناء System Prompt
    system_prompt = f"""أنت {agent_name}، مندوب مبيعات ذكي يعمل لدى {company_name}.

لهجة الرد: {tone}

معلومات الشركة والخدمات:
{description}

{f"بيانات المنتجات والمخزون الحالي (JSON):{chr(10)}{store_data}" if store_data else ""}

قواعد مهمة:
- رد دائماً بالعربية ما لم يتحدث العميل بلغة أخرى
- كن مقنعاً ومحترماً ومركزاً على إتمام البيع
- إذا سُئلت عن سعر غير موجود في البيانات، قل أنك ستتحقق وتعود للعميل
- لا تذكر أنك ذكاء اصطناعي إلا إذا سُئلت مباشرة
- الردود تكون مختصرة وواضحة (حد أقصى 3 فقرات قصيرة)
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_message}
    ]

    # 5. استدعاء API حسب المزود
    try:
        if provider == "openai":
            response = await _call_openai(api_key, model_id, messages)
        elif provider == "anthropic":
            response = await _call_anthropic(api_key, model_id, messages, system_prompt)
        elif provider == "groq":
            response = await _call_groq(api_key, model_id, messages)
        elif provider == "google":
            response = await _call_google(api_key, model_id, user_message, system_prompt)
        else:
            response = await _call_openai(api_key, model_id, messages)

        # 6. تسجيل السجل
        _log_message(supabase, client_id, user_message, response, phone_number, channel)
        return response

    except Exception as e:
        print(f"AI call error: {e}")
        return "عذراً، حدث خطأ أثناء معالجة طلبك. يرجى المحاولة مرة أخرى."


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


async def _call_google(api_key: str, model_id: str, user_message: str, system: str) -> str:
    clean_model_id = model_id.strip().lower()
    clean_api_key = api_key.strip()
    
    if not clean_model_id.startswith("models/"):
        full_model_name = f"models/{clean_model_id}"
    else:
        full_model_name = clean_model_id
        
    url = f"https://generativelanguage.googleapis.com/v1beta/{full_model_name}:generateContent?key={clean_api_key}"
    headers = {"Content-Type": "application/json"}
    body = {
        "systemInstruction": {
            "parts": [{"text": system}]
        },
        "contents": [
            {
                "role": "user",
                "parts": [{"text": user_message}]
            }
        ],
        "generationConfig": {"maxOutputTokens": 500}
    }
    async with httpx.AsyncClient() as client:
        res = await client.post(url, headers=headers, json=body, timeout=30)
        data = res.json()
        if res.status_code != 200:
            error_msg = data.get("error", {}).get("message", "Unknown Google error")
            raise Exception(f"Google API Error: {error_msg}")
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except (KeyError, IndexError):
            raise Exception("Unexpected Google API response format")


def _log_message(supabase, client_id: str, user_message: str, ai_response: str, phone_number: str, channel: str = "whatsapp_evolution"):
    try:
        supabase.table("message_logs").insert({
            "client_id": client_id,
            "channel": channel if channel != "unknown" else "whatsapp_evolution",
            "direction": "in",
            "phone_number": phone_number,
            "message_text": user_message,
            "ai_response": ai_response
        }).execute()
    except Exception as e:
        print(f"Log error: {e}")
