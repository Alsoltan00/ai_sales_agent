import os
import json
import httpx
from database.db_client import get_supabase_client


async def get_ai_response(client_id: str, phone_number: str, user_message: str,
                          image_base64: str = None, audio_base64: str = None,
                          message_id: str = None, channel: str = "whatsapp"):
    """
    High-Precision AI Engine v4.0
    - Strict data injection from DB (no hallucination)
    - Full error logging for diagnosis
    - Correct OR query support
    """
    supabase = get_supabase_client()

    # ─── 1. MERCHANT IDENTITY ────────────────────────────────────────────────
    client_res = supabase.table("clients").select("*").eq("id", client_id).single().execute()
    if not client_res.data:
        print(f"[ENGINE] ERROR: Client {client_id} not found.")
        return "عذراً، المتجر غير موجود."

    c = client_res.data
    agent_name  = c.get("agent_name", "نوره")
    company_name = c.get("company_name", "المتجر")
    store_activity = c.get("store_activity", "تجارة")
    description = c.get("description", "")
    base_tone   = c.get("ai_tone", "حماسي وتسويقي")
    messages_used = c.get("messages_used", 0)
    message_limit = c.get("message_limit", 1000)

    if messages_used >= message_limit:
        return "نعتذر، انتهى رصيد الرسائل للمتجر."

    print(f"[ENGINE] Client: {company_name} | Agent: {agent_name} | Provider TBD")

    # ─── 2. AI MODEL RESOLUTION (Plan → Config) ──────────────────────────────
    api_key, model_id, provider = None, "gpt-3.5-turbo", "openai"
    try:
        # Check plan-assigned model first
        plan_name = c.get("subscription_plan")
        if plan_name:
            p_det = supabase.table("subscription_plans").select("permissions").eq("name", plan_name).single().execute()
            if p_det.data:
                perms = p_det.data.get("permissions", {})
                if isinstance(perms, str):
                    perms = json.loads(perms)
                mid = perms.get("assigned_model_id")
                if mid:
                    gm = supabase.table("global_ai_models").select("*").eq("id", mid).single().execute()
                    if gm.data:
                        api_key  = gm.data["api_key"]
                        model_id = gm.data["model_id"]
                        provider = gm.data["provider"].lower()
                        print(f"[ENGINE] Model from PLAN: {model_id} via {provider}")

        # Fallback: merchant's own active config
        if not api_key:
            m_cfg = supabase.table("ai_models_config").select("*").eq("client_id", client_id).eq("is_active", True).execute()
            if m_cfg.data:
                api_key  = m_cfg.data[0]["api_key"]
                model_id = m_cfg.data[0]["model_id"]
                provider = m_cfg.data[0]["provider"].lower()
                print(f"[ENGINE] Model from CONFIG: {model_id} via {provider}")

        if not api_key:
            print(f"[ENGINE] ERROR: No API key found for client {client_id}")

    except Exception as e:
        print(f"[ENGINE] Model resolution error: {e}")

    # ─── 3. COLUMN TRAINING → STRICT BEHAVIORAL RULES ────────────────────────
    col_behavior_rules = ""
    col_display_map = ""
    try:
        col_res = supabase.table("column_training").select("column_name, note").eq("client_id", client_id).execute()
        if col_res.data:
            rules_list = []
            display_list = []
            for item in col_res.data:
                col  = item.get("column_name", "")
                note = (item.get("note") or "").strip()
                if not note:
                    continue
                # Any note is a behavioral instruction, not just a label
                rules_list.append(f"- بخصوص عمود [{col}]: {note}")
                display_list.append(f"  • {col} = {note[:60]}")
            
            if rules_list:
                col_behavior_rules = "## تعليمات سلوكية إلزامية مستخرجة من إعدادات التاجر:\n" + "\n".join(rules_list)
                col_display_map = "\n".join(display_list)
                print(f"[ENGINE] Column behavioral rules: {len(rules_list)} rules loaded")
    except Exception as e:
        print(f"[ENGINE] Column training error: {e}")

    # ─── 4. PRODUCT DATA (Smart Keyword Search) ───────────────────────────────
    product_section = ""
    try:
        data_res = supabase.table("merchant_manual_data").select("data").eq("client_id", client_id).execute()
        if data_res.data and data_res.data[0].get("data"):
            all_rows = data_res.data[0]["data"]
            total = len(all_rows)
            print(f"[ENGINE] Total products in DB: {total}")

            # Extract keywords from user message (≥2 chars)
            keywords = [k.strip() for k in user_message.replace("؟","").replace("?","").split() if len(k.strip()) >= 2]

            # Score rows by keyword relevance
            scored = []
            for row in all_rows:
                row_text = " ".join(str(v) for v in row.values()).lower()
                score = sum(1 for kw in keywords if kw.lower() in row_text)
                scored.append((score, row))

            # Sort: matched rows first, then rest
            scored.sort(key=lambda x: x[0], reverse=True)

            # Take top 30 relevant + up to 10 general
            relevant = [r for s, r in scored if s > 0][:30]
            general  = [r for s, r in scored if s == 0][:10]
            final_rows = relevant + general

            print(f"[ENGINE] Matched rows: {len(relevant)} | General fill: {len(general)}")

            # Build clean readable lines
            lines = []
            for row in final_rows:
                parts = []
                for k, v in row.items():
                    # Skip Unix timestamps (13-digit numbers)
                    v_str = str(v)
                    if v_str.isdigit() and len(v_str) >= 13:
                        continue
                    parts.append(f"{k}: {v}")
                if parts:
                    lines.append("• " + " | ".join(parts))

            if lines:
                tag = "✅ نتائج مطابقة لطلبك:\n" if relevant else ""
                product_section = tag + "\n".join(lines)
            else:
                product_section = "لا توجد منتجات مسجلة."
        else:
            print(f"[ENGINE] No product data found for client {client_id}")
            product_section = "لا توجد منتجات مسجلة حالياً."
    except Exception as e:
        print(f"[ENGINE] Product data error: {e}")
        product_section = "تعذّر تحميل قائمة المنتجات."

    # ─── 5. BUSINESS RULES ────────────────────────────────────────────────────
    rules_section = ""
    try:
        r_res = supabase.table("business_rules").select("rules_data").eq("client_id", client_id).single().execute()
        if r_res.data and r_res.data.get("rules_data"):
            rd = r_res.data["rules_data"]
            checkout_type = rd.get("checkout_type", "store")

            if checkout_type == "chat":
                payments = []
                if rd.get("chat_payment_cod"):      payments.append("الدفع عند الاستلام (COD)")
                if rd.get("chat_payment_transfer"): payments.append(f"تحويل بنكي — {rd.get('bank_accounts','')}")
                if rd.get("chat_payment_link"):     payments.append(f"رابط دفع — {rd.get('payment_links','')}")
                checkout_rule = f"إتمام الطلب داخل الواتساب. طرق الدفع: {', '.join(payments) or 'حسب الاتفاق'}."
                order_rule    = "اطلب (الاسم + العنوان + الكمية) فقط بعد أن يؤكد العميل رغبته في الشراء."
            else:
                checkout_rule = "وجّه العميل لإتمام الشراء عبر رابط المتجر الإلكتروني."
                order_rule    = "لا تطلب بيانات العميل، فقط أرسل رابط المنتج."

            rules_section = f"""
## دستور العمل (التزم به حرفياً):
- **مسار الطلب:** {checkout_rule}
- **إتمام البيع:** {order_rule}
- **الخصومات:** {rd.get('discount_msg', 'لا توجد خصومات حالية.')}
- **الشكاوى:** {rd.get('complaint_msg', 'أبدِ تعاطفاً وأبلغ الإدارة.')}
"""
    except Exception as e:
        print(f"[ENGINE] Business rules error: {e}")

    # ─── 6. FINAL SYSTEM PROMPT ───────────────────────────────────────────────
    system_prompt = f"""أنت "{agent_name}"، موظف مبيعات في "{company_name}".
نشاط المتجر: {store_activity}.
{f'نبذة: {description}' if description else ''}
نبرة الصوت: {base_tone}.

## قواعد الحوار (صارمة):
1. تحدث كإنسان طبيعي. لا تذكر مصطلحات تقنية (قاعدة بيانات، نظام، رقم جوال).
2. لا تكرر التعريف بنفسك إذا وُجدت رسائل سابقة.
3. لا تستخدم قوائم نقطية في رسالة الترحيب الأولى.
4. لا تطلب بيانات العميل الشخصية إلا عند تأكيد الطلب النهائي.

{col_behavior_rules}

## قائمة المنتجات المتوفرة (المصدر الوحيد للحقيقة):
{product_section}

{rules_section}

## قانون منع الهلوسة (غير قابل للكسر):
- لا تذكر أي منتج غير موجود في القائمة أعلاه. إذا لم يُطلب، قل: "غير متوفر حالياً."
- لا تذكر أي ماركة (Garnier, L'Oreal, إلخ) إلا إذا كانت مكتوبة صراحةً في القائمة.
- إذا قال العميل "الأول" أو "هذا"، راجع آخر منتج ذكرته أنت في ردك السابق مباشرة.
"""

    # ─── 7. CONVERSATION HISTORY ──────────────────────────────────────────────
    history = []
    search_phone = phone_number.split("@")[0]
    try:
        # Fetch last 8 exchanges ordered by time ascending
        h_res = supabase.table("message_logs") \
            .select("message_text, ai_response") \
            .or_(f"phone_number.eq.{search_phone},phone_number.eq.{phone_number}") \
            .eq("client_id", client_id) \
            .order("timestamp", desc=True) \
            .limit(8) \
            .execute()

        if h_res.data:
            for m in reversed(h_res.data):
                u = (m.get("message_text") or "").strip()
                a = (m.get("ai_response") or "").strip()
                if u: history.append({"role": "user",      "content": u})
                if a: history.append({"role": "assistant", "content": a})
            print(f"[ENGINE] History loaded: {len(history)} messages")
        else:
            print(f"[ENGINE] No history for {search_phone}")
    except Exception as e:
        print(f"[ENGINE] History error: {e}")

    # ─── 8. BUILD MESSAGE PAYLOAD ─────────────────────────────────────────────
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)

    if image_base64:
        messages.append({"role": "user", "content": [
            {"type": "text",      "text": user_message or "حلل هذه الصورة"},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
        ]})
    else:
        messages.append({"role": "user", "content": user_message})

    print(f"[ENGINE] Sending {len(messages)} messages to {provider}/{model_id}")

    # ─── 9. LLM CALL ──────────────────────────────────────────────────────────
    try:
        if not api_key:
            raise ValueError(f"No API key for provider '{provider}'. Check ai_models_config.")

        if   provider == "openai":     response = await _call_openai(api_key, model_id, messages)
        elif provider == "google":     response = await _call_google(api_key, model_id, messages, system_prompt)
        elif provider == "openrouter": response = await _call_openrouter(api_key, model_id, messages)
        elif provider == "groq":       response = await _call_groq(api_key, model_id, messages)
        elif provider == "anthropic":  response = await _call_anthropic(api_key, model_id, messages, system_prompt)
        else:
            print(f"[ENGINE] Unknown provider '{provider}', falling back to openrouter")
            response = await _call_openrouter(api_key, model_id, messages)

        _log_message(supabase, client_id, user_message, response, phone_number, channel, message_id)
        supabase.table("clients").update({"messages_used": messages_used + 1}).eq("id", client_id).execute()
        print(f"[ENGINE] Response OK ({len(response)} chars)")
        return response

    except Exception as e:
        print(f"[ENGINE] CRITICAL LLM ERROR [{provider}]: {e}")
        return f"عذراً، واجهت مشكلة تقنية. يرجى التواصل مع المتجر مباشرة."


# ─── PROVIDER IMPLEMENTATIONS ─────────────────────────────────────────────────

async def _call_openai(api_key: str, model_id: str, messages: list) -> str:
    async with httpx.AsyncClient(timeout=45) as c:
        r = await c.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model_id, "messages": messages, "temperature": 0.1, "max_tokens": 600}
        )
        data = r.json()
        if "choices" not in data:
            raise Exception(f"OpenAI error: {data.get('error', {}).get('message', str(data))}")
        return data["choices"][0]["message"]["content"].strip()


async def _call_openrouter(api_key: str, model_id: str, messages: list) -> str:
    async with httpx.AsyncClient(timeout=45) as c:
        r = await c.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model_id, "messages": messages, "temperature": 0.1, "max_tokens": 600}
        )
        data = r.json()
        if "choices" not in data:
            raise Exception(f"OpenRouter error: {data.get('error', {}).get('message', str(data))}")
        return data["choices"][0]["message"]["content"].strip()


async def _call_groq(api_key: str, model_id: str, messages: list) -> str:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model_id, "messages": messages, "temperature": 0.1, "max_tokens": 600}
        )
        data = r.json()
        if "choices" not in data:
            raise Exception(f"Groq error: {data.get('error', {}).get('message', str(data))}")
        return data["choices"][0]["message"]["content"].strip()


async def _call_anthropic(api_key: str, model_id: str, messages: list, system: str) -> str:
    user_msgs = [m for m in messages if m["role"] != "system"]
    async with httpx.AsyncClient(timeout=45) as c:
        r = await c.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            json={"model": model_id, "system": system, "messages": user_msgs, "max_tokens": 600}
        )
        data = r.json()
        if "content" not in data:
            raise Exception(f"Anthropic error: {data.get('error', {}).get('message', str(data))}")
        return data["content"][0]["text"].strip()


async def _call_google(api_key: str, model_id: str, messages: list, system: str) -> str:
    m_id = model_id.strip()
    if not m_id.startswith("models/"):
        m_id = f"models/{m_id}"
    url = f"https://generativelanguage.googleapis.com/v1beta/{m_id}:generateContent?key={api_key}"

    contents = []
    for msg in messages:
        if msg["role"] == "system":
            continue
        role = "user" if msg["role"] == "user" else "model"
        parts = []
        if isinstance(msg["content"], str):
            parts = [{"text": msg["content"]}]
        elif isinstance(msg["content"], list):
            for p in msg["content"]:
                if p["type"] == "text":
                    parts.append({"text": p["text"]})
                elif p["type"] == "image_url":
                    b64 = p["image_url"]["url"].split(",")[-1]
                    parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})
        contents.append({"role": role, "parts": parts})

    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 600}
    }
    async with httpx.AsyncClient(timeout=45) as c:
        r = await c.post(url, json=body)
        data = r.json()
        if r.status_code != 200:
            raise Exception(f"Google error: {data.get('error', {}).get('message', str(data))}")
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()


# ─── LOGGING ──────────────────────────────────────────────────────────────────

def _log_message(supabase, client_id: str, user_msg: str, ai_res: str,
                 phone: str, channel: str, msg_id: str):
    try:
        supabase.table("message_logs").insert({
            "client_id":    client_id,
            "phone_number": phone,
            "message_text": user_msg,
            "ai_response":  ai_res,
            "channel":      channel,
            "message_id":   msg_id
        }).execute()
    except Exception as e:
        print(f"[ENGINE] Log error: {e}")