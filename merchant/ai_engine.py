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
    Professional Version 2.0 - Fully Structured and Anti-Hallucination
    """
    supabase = get_supabase_client()
    
    # 1. Fetch client/merchant settings
    client_res = supabase.table("clients").select("*").eq("id", client_id).single().execute()
    if not client_res.data:
        return "عذراً، لم يتم العثور على إعدادات هذا المتجر."
    
    client = client_res.data
    agent_name = client.get("agent_name", "نوره")
    company_name = client.get("company_name", "متجرنا")
    store_activity = client.get("store_activity", "تجارة عامة")
    description = client.get("description", "")
    tone = client.get("ai_tone", "friendly")
    messages_used = client.get("messages_used", 0)
    message_limit = client.get("message_limit", 1000)

    # 2. AI Model Source Resolution (Priority: Plan > Merchant Config)
    api_key = None
    model_id = "gpt-3.5-turbo"
    provider = "openai"
    
    try:
        # Check Plan Override
        plan_res = supabase.table("clients").select("subscription_plan").eq("id", client_id).single().execute()
        if plan_res.data and plan_res.data.get("subscription_plan"):
            plan_name = plan_res.data["subscription_plan"]
            plan_details = supabase.table("subscription_plans").select("permissions").eq("name", plan_name).single().execute()
            if plan_details.data:
                perms = plan_details.data.get("permissions", {})
                if isinstance(perms, str):
                    try: perms = json.loads(perms)
                    except: perms = {}
                
                assigned_model_id = perms.get("assigned_model_id")
                if assigned_model_id:
                    g_model = supabase.table("global_ai_models").select("*").eq("id", assigned_model_id).single().execute()
                    if g_model.data:
                        api_key = g_model.data.get("api_key")
                        model_id = g_model.data.get("model_id")
                        provider = g_model.data.get("provider", "openai").lower()

        # Fallback to Merchant Config
        if not api_key:
            model_res = supabase.table("ai_models_config").select("*").eq("client_id", client_id).eq("is_active", True).execute()
            if model_res.data:
                m_cfg = model_res.data[0]
                api_key = m_cfg.get("api_key")
                model_id = m_cfg.get("model_id")
                provider = m_cfg.get("provider", "openai").lower()
    except Exception as e:
        print(f"Warning: AI config resolution failed: {e}")

    if messages_used >= message_limit:
        return "نعتذر منك، لقد انتهى الرصيد المخصص للرسائل لهذا المتجر حالياً."

    # 3. Data Context Preparation (Markdown Structured)
    store_data = ""
    try:
        data_res = supabase.table("merchant_manual_data").select("data").eq("client_id", client_id).execute()
        if data_res.data:
            rows = data_res.data[0].get("data", [])
            if rows:
                lines = []
                for item in rows:
                    lines.append(" | ".join([f"{k}: {v}" for k, v in item.items()]))
                store_data = "\n".join([f"- {l}" for l in lines])
    except Exception as e:
        print(f"Warning: Data fetch failed: {e}")

    # 4. Business Rules Logic
    checkout_instructions = "إتمام الطلب عبر المتجر الإلكتروني."
    business_rules_text = ""
    try:
        rules_res = supabase.table("business_rules").select("rules_data").eq("client_id", client_id).single().execute()
        if rules_res.data and rules_res.data.get("rules_data"):
            rd = rules_res.data["rules_data"]
            if rd.get('checkout_type') == 'chat':
                pm = []
                if rd.get('chat_payment_cod'): pm.append("الدفع عند الاستلام")
                if rd.get('chat_payment_transfer'): pm.append(f"تحويل بنكي ({rd.get('bank_accounts', '')})")
                if rd.get('chat_payment_link'): pm.append(f"رابط دفع ({rd.get('payment_links', '')})")
                checkout_instructions = f"إتمام الطلب داخل المحادثة. طرق الدفع: {', '.join(pm)}. اطلب بيانات العميل (الاسم، العنوان، الجوال) فقط عند التأكيد النهائي للشراء."
            
            business_rules_text = f"""
### قواعد العمل الصارمة:
- **مسار الطلب:** {checkout_instructions}
- **سياسة الخصم:** {rd.get('discount_type', 'حسب السياسة')}. {rd.get('discount_msg', '')}
- **نبرة الصوت:** {rd.get('tone_type', tone)}.
- **الشكاوى:** {rd.get('complaint_msg', 'سيتم التعامل مع شكواك فوراً.')}
"""
    except Exception: pass

    # 5. Professional System Prompt (The Brain)
    final_system_prompt = f"""# الهوية والوظيفة
أنت المساعد الذكي "{agent_name}" من "{company_name}".
نشاطنا: {store_activity}.
وصف المتجر: {description}.

# قواعد الحوار (صارمة)
- **ممنوع تماماً** ذكر أنك "استلمت رقم الجوال" أو "النظام تعرف عليك". تعامل كأنك في محادثة واتساب طبيعية.
- **ممنوع** استخدام أسلوب القوائم (النقاط) في الترحيب أو الردود الأولى.
- ابدأ بالترحيب وتقديم المساعدة مباشرة (مثال: "أهلاً بك في متجر أصيل، كيف أقدر أخدمك اليوم؟").
- لا تطلب أي بيانات (منتج، كمية، اسم) إلا إذا طلب العميل ذلك أو سأل عن الشراء.
- كن بائعاً شاطراً، إذا سأل العميل "ماذا لديكم"، اقترح عليه أفضل التصنيفات أو المنتجات بأسلوب قصصي مشوق.

# قائمة المنتجات المتوفرة (المصدر الوحيد للحقيقة)
{store_data if store_data else "لا توجد منتجات مسجلة حالياً."}

# تعليمات منع الهلوسة والذاكرة
- **القاعدة الذهبية:** لا تقم باختراع أي منتج أو سعر غير موجود في القائمة أعلاه. إذا سأل العميل عن شيء غير متوفر، اعتذر بلباقة.
- **حل الإشارات:** إذا قال العميل "الأول" أو "أعطني هذا"، انظر فوراً لآخر رسالة أرسلتها أنت لتعرف المنتج الذي كنت تتحدث عنه.
- **الخصوصية:** لا تطلب بيانات العميل الشخصية (الاسم/الجوال) إلا في نهاية عملية البيع لتأكيد الطلب.

{business_rules_text}
"""

    # 6. History Management with Normalization
    chat_history = []
    search_phone = phone_number.split("@")[0]
    try:
        h_res = supabase.table("message_logs") \
            .select("message_text, ai_response, timestamp") \
            .or_(f"phone_number.eq.{search_phone},phone_number.eq.{phone_number}") \
            .eq("client_id", client_id) \
            .order("timestamp", desc=True) \
            .limit(8) \
            .execute()
        
        if h_res.data:
            # Sort chronologically
            sorted_h = sorted(h_res.data, key=lambda x: x.get("timestamp", ""))
            for m in sorted_h:
                u_txt = (m.get("message_text") or "").strip()
                a_txt = (m.get("ai_response") or "").strip()
                if u_txt: chat_history.append({"role": "user", "content": u_txt})
                if a_txt: chat_history.append({"role": "assistant", "content": a_txt})
    except Exception: pass

    # Build Messages Payload
    final_messages = [{"role": "system", "content": final_system_prompt}]
    final_messages.extend(chat_history)
    
    if image_base64:
        content = [{"type": "text", "text": user_message or "حلل هذه الصورة"}]
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}})
        final_messages.append({"role": "user", "content": content})
    else:
        final_messages.append({"role": "user", "content": user_message})

    # 7. Execution and Logging
    try:
        if not api_key: raise Exception("API Key missing")
        
        # Universal Provider Routing
        if provider == "openai":
            response = await _call_openai(api_key, model_id, final_messages)
        elif provider == "google":
            response = await _call_google(api_key, model_id, final_messages, final_system_prompt)
        elif provider == "groq":
            response = await _call_groq(api_key, model_id, final_messages)
        elif provider == "anthropic":
            response = await _call_anthropic(api_key, model_id, final_messages, final_system_prompt)
        elif provider == "openrouter":
            response = await _call_openrouter(api_key, model_id, final_messages)
        else:
            response = await _call_openrouter(api_key, model_id, final_messages)

        # Update and Log
        _log_message(supabase, client_id, user_message, response, phone_number, channel, message_id)
        supabase.table("clients").update({"messages_used": messages_used + 1}).eq("id", client_id).execute()
        return response

    except Exception as e:
        print(f"CRITICAL AI ERROR [{client_id}]: {e}")
        return f"عذراً، واجهت مشكلة تقنية (ERR_AI_{provider.upper()}). يرجى التحقق من إعدادات النموذج."

async def _call_openai(api_key: str, model_id: str, messages: list) -> str:
    async with httpx.AsyncClient() as client:
        res = await client.post("https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model_id, "messages": messages, "max_tokens": 500, "temperature": 0.1},
            timeout=30)
        data = res.json()
        if "choices" not in data: raise Exception(f"OpenAI: {data.get('error', {}).get('message', 'Error')}")
        return data["choices"][0]["message"]["content"].strip()

async def _call_google(api_key: str, model_id: str, messages: list, system: str) -> str:
    m_id = model_id.strip()
    if not m_id.startswith("models/"): m_id = f"models/{m_id}"
    url = f"https://generativelanguage.googleapis.com/v1beta/{m_id}:generateContent?key={api_key}"
    contents = []
    for msg in messages:
        if msg["role"] == "system": continue
        role = "user" if msg["role"] == "user" else "model"
        parts = []
        if isinstance(msg["content"], str): parts.append({"text": msg["content"]})
        elif isinstance(msg["content"], list):
            for p in msg["content"]:
                if p["type"] == "text": parts.append({"text": p["text"]})
                elif p["type"] == "image_url":
                    b64 = p["image_url"]["url"].split(",")[-1]
                    parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})
        contents.append({"role": role, "parts": parts})
    
    body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents, "generationConfig": {"maxOutputTokens": 500, "temperature": 0.1}}
    async with httpx.AsyncClient() as client:
        res = await client.post(url, json=body, timeout=30)
        data = res.json()
        if res.status_code != 200: raise Exception(f"Google: {data.get('error', {}).get('message', 'Error')}")
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()

async def _call_groq(api_key: str, model_id: str, messages: list) -> str:
    async with httpx.AsyncClient() as client:
        res = await client.post("https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model_id, "messages": messages, "temperature": 0.1},
            timeout=30)
        data = res.json()
        if "choices" not in data: raise Exception(f"Groq: {data.get('error', {}).get('message', 'Error')}")
        return data["choices"][0]["message"]["content"].strip()

async def _call_anthropic(api_key: str, model_id: str, messages: list, system: str) -> str:
    u_msgs = [m for m in messages if m["role"] != "system"]
    async with httpx.AsyncClient() as client:
        res = await client.post("https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
            json={"model": model_id, "system": system, "messages": u_msgs, "max_tokens": 500},
            timeout=30)
        data = res.json()
        if "content" not in data: raise Exception(f"Anthropic: {data.get('error', {}).get('message', 'Error')}")
        return data["content"][0]["text"].strip()

async def _call_openrouter(api_key: str, model_id: str, messages: list) -> str:
    async with httpx.AsyncClient() as client:
        res = await client.post("https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model_id, "messages": messages},
            timeout=30)
        data = res.json()
        if "choices" not in data: raise Exception(f"OpenRouter: {data.get('error', {}).get('message', 'Error')}")
        return data["choices"][0]["message"]["content"].strip()

def _log_message(supabase, client_id: str, user_message: str, ai_response: str, phone_number: str, channel: str = "whatsapp", message_id: str = None):
    try:
        supabase.table("message_logs").insert({
            "client_id": client_id, "channel": channel, "direction": "in",
            "phone_number": phone_number, "message_text": user_message,
            "ai_response": ai_response, "message_id": message_id
        }).execute()
    except Exception as e:
        print(f"Log error: {e}")