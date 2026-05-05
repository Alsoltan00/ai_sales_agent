import os\nimport json\nimport httpx\nfrom database.db_client import get_supabase_client\n\ndef _normalize_col_name(name: str) -> str:\n    if not isinstance(name, str):\n        return ""\n    return " ".join(name.strip().lower().split())\n\nasync def get_ai_response(client_id: str, phone_number: str, user_message: str, 
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

    # 2. Fetch Merchant Data (Products/Knowledge Base)
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

    # 3. Fetch Column Training / Field Rules
    column_training_prompt = ""
    try:
        col_res = supabase.table("column_training").select("column_name, column_note").eq("client_id", client_id).execute()
        if col_res.data:
            notes = [f"- {c['column_name']}: {c['column_note']}" for c in col_res.data]
            column_training_prompt = "تعليمات خاصة بأعمدة البيانات:\n" + "\n".join(notes)
    except Exception as e:
        print(f"Warning: Could not fetch column training: {e}")

    # 4. Fetch Business Rules (Smart Policies)
    business_rules_prompt = ""
    try:
        rules_res = supabase.table("business_rules").select("rules_data").eq("client_id", client_id).single().execute()
        if rules_res.data and rules_res.data.get("rules_data"):
            rd = rules_res.data["rules_data"]
            checkout = rd.get('checkout_type', 'store')
            
            if checkout == 'chat':
                checkout_instructions = "مسار إتمام الطلب: داخل المحادثة (واتساب). يجب عليك أخذ بيانات العميل (الاسم، الجوال، العنوان) وتأكيد الطلب بالكامل داخل المحادثة."
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
- عند نفاذ المخزون: {rd.get('stock_out_type', 'الاعتذار')}. {rd.get('stock_out_msg', '')}
- نبرة الصوت: {rd.get('tone_type', tone)}. {rd.get('complaint_msg', '')}
- حواجز الحماية: {rd.get('ban_custom', '')}
"""
    except Exception as e:
        print(f"Warning: Could not fetch business rules: {e}")

    # 5. Build Product Context with reference warning
    product_context = ""
    if store_data:
        product_context = f"""
بيانات المنتجات والمخزون المتاحة حالياً:
-------------------------------------------
{store_data}
-------------------------------------------
{column_training_prompt}
ملاحظة هامة (تفسير طلب العميل): 
- إذا استخدم العميل كلمات إشارة مثل (الأول، الثاني، الأخير، هذا، اللي فوق)، يجب عليك تجاهل القائمة أعلاه والذهاب فوراً لرسالتك السابقة في سجل المحادثة.
- استخدم البيانات أعلاه حصراً للأسعار والمخزون الجديد.
"""

    # 6. Build Core System Prompt (NO history here)
    system_prompt = f"""هويتك الشخصية:
- اسمك هو "{agent_name}" من "{company_name}".
- قواعد التعريف بالنفس: عرف بنفسك في أول رسالة فقط. يمنع تكرار التعريف في حال وجود سجل محادثة.
- وظيفتك: مساعدة العميل في الشراء من نشاط [{store_activity}].

معلومات المتجر: {description}

{product_context}

{business_rules_prompt}

قواعد عامة:
- تحدث بلهجة العميل.
- لا تخترع منتجات.
- كن مختصراً وودوداً.
"""

    # 7. Fetch REAL Chat History Messages (Correct Role-based)
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

    # 8. Construct final messages array
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(chat_history_messages[-8:]) # Last 8 turns

    # Add current message
    if image_base64:
        content = [{"type": "text", "text": user_message or "حلل الصورة"}]
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}})
        messages.append({"role": "user", "content": content})
    else:
        messages.append({"role": "user", "content": user_message})

    # 9. Call LLM
    try:
        if provider == "openai":
            response = await _call_openai(api_key, model_id, messages)
        elif provider == "google":
            response = await _call_google(api_key, model_id, messages, system_prompt)
        elif provider == "groq":
            response = await _call_groq(api_key, model_id, messages)
        elif provider == "openrouter":
            response = await _call_openrouter(api_key, model_id, messages)
        else:
            response = await _call_openai(api_key, model_id, messages)

        # Log and increment
        _log_message(supabase, client_id, user_message, response, phone_number, channel, message_id)
        supabase.table("clients").update({"messages_used": messages_used + 1}).eq("id", client_id).execute()
        
        return response
    except Exception as e:
        print(f"AI Error: {e}")
        return "عذراً، واجهت مشكلة فنية بسيطة. يرجى إعادة المحاولة."
\nasync def _call_openai(api_key: str, model_id: str, messages: list) -> str:\n    async with httpx.AsyncClient() as client:\n        res = await client.post(\n            "https://api.openai.com/v1/chat/completions",\n            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},\n            json={"model": model_id, "messages": messages, "max_tokens": 500, "temperature": 0.1},\n            timeout=30\n        )\n        data = res.json()\n        if "choices" not in data:\n            print(f"[OpenAI API Error] Response: {data}")\n            return "عذراً، يبدو أن هناك ضغطاً على خوادم الذكاء الاصطناعي (OpenAI). يرجى المحاولة بعد قليل."\n        return data["choices"][0]["message"]["content"].strip()\n\n\nasync def _call_anthropic(api_key: str, model_id: str, messages: list, system: str) -> str:\n    # Anthropic requires system as a top-level field\n    user_messages = [m for m in messages if m["role"] != "system"]\n    async with httpx.AsyncClient() as client:\n        res = await client.post(\n            "https://api.anthropic.com/v1/messages",\n            headers={\n                "x-api-key": api_key,\n                "anthropic-version": "2023-06-01",\n                "Content-Type": "application/json"\n            },\n            json={"model": model_id, "system": system, "messages": user_messages, "max_tokens": 500, "temperature": 0.1},\n            timeout=30\n        )\n        data = res.json()\n        if "content" not in data:\n            print(f"[Anthropic API Error] Response: {data}")\n            return "عذراً، يبدو أن هناك ضغطاً على خوادم الذكاء الاصطناعي (Anthropic). يرجى المحاولة بعد قليل."\n        return data["content"][0]["text"].strip()\n\n\nasync def _call_groq(api_key: str, model_id: str, messages: list) -> str:\n    async with httpx.AsyncClient() as client:\n        res = await client.post(\n            "https://api.groq.com/openai/v1/chat/completions",\n            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},\n            json={"model": model_id, "messages": messages, "max_tokens": 500, "temperature": 0.1},\n            timeout=30\n        )\n        data = res.json()\n        if "choices" not in data:\n            print(f"[Groq API Error] Response: {data}")\n            return "عذراً، يبدو أن هناك ضغطاً على خوادم الذكاء الاصطناعي (Groq Rate Limit). يرجى المحاولة بعد قليل."\n        return data["choices"][0]["message"]["content"].strip()\n\n\nasync def _call_google(api_key: str, model_id: str, messages: list, system: str) -> str:\n    """\n    Fixed Google Gemini API call that correctly maps OpenAI-style messages to Gemini contents with history.\n    """\n    clean_model_id = model_id.strip().lower()\n    clean_api_key = api_key.strip()\n    \n    if not clean_model_id.startswith("models/"):\n        full_model_name = f"models/{clean_model_id}"\n    else:\n        full_model_name = clean_model_id\n        \n    url = f"https://generativelanguage.googleapis.com/v1beta/{full_model_name}:generateContent?key={clean_api_key}"\n    headers = {"Content-Type": "application/json"}\n    \n    # Map messages to Gemini contents\n    contents = []\n    for msg in messages:\n        if msg["role"] == "system": continue\n        \n        role = "user" if msg["role"] == "user" else "model"\n        \n        parts = []\n        if isinstance(msg["content"], str):\n            parts.append({"text": msg["content"]})\n        elif isinstance(msg["content"], list):\n            for part in msg["content"]:\n                if part["type"] == "text":\n                    parts.append({"text": part["text"]})\n                elif part["type"] == "image_url":\n                    # Extract base64 from data:image/jpeg;base64,...\n                    b64 = part["image_url"]["url"].split(",")[-1]\n                    parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})\n        \n        contents.append({"role": role, "parts": parts})\n\n    body = {\n        "systemInstruction": {\n            "parts": [{"text": system}]\n        },\n        "contents": contents,\n        "generationConfig": {"maxOutputTokens": 500, "temperature": 0.1}\n    }\n    async with httpx.AsyncClient() as client:\n        res = await client.post(url, headers=headers, json=body, timeout=30)\n        data = res.json()\n        if res.status_code != 200:\n            error_msg = data.get("error", {}).get("message", "Unknown Google error")\n            raise Exception(f"Google API Error: {error_msg}")\n        try:\n            return data["candidates"][0]["content"]["parts"][0]["text"].strip()\n        except (KeyError, IndexError):\n            raise Exception("Unexpected Google API response format")\n\nasync def _call_openrouter(api_key: str, model_id: str, messages: list) -> str:\n    async with httpx.AsyncClient() as client:\n        res = await client.post(\n            "https://openrouter.ai/api/v1/chat/completions",\n            headers={\n                "Authorization": f"Bearer {api_key}",\n                "Content-Type": "application/json",\n                "HTTP-Referer": "https://ai-sales-agent-dreu.onrender.com",\n                "X-Title": "AI Sales Agent"\n            },\n            json={"model": model_id, "messages": messages, "max_tokens": 500, "temperature": 0.1},\n            timeout=30\n        )\n        data = res.json()\n        if "choices" in data:\n            return data["choices"][0]["message"]["content"].strip()\n        else:\n            error_msg = data.get("error", {}).get("message", "Unknown OpenRouter error")\n            print(f"[OpenRouter API Error] Response: {data}")\n            return "عذراً، يبدو أن هناك ضغطاً على خوادم الذكاء الاصطناعي (OpenRouter). يرجى المحاولة بعد قليل."\n\n\ndef _log_message(supabase, client_id: str, user_message: str, ai_response: str, phone_number: str, channel: str = "whatsapp_evolution", message_id: str = None):\n    try:\n        supabase.table("message_logs").insert({\n            "client_id": client_id,\n            "channel": channel if channel != "unknown" else "whatsapp_evolution",\n            "direction": "in",\n            "phone_number": phone_number,\n            "message_text": user_message,\n            "ai_response": ai_response,\n            "message_id": message_id\n        }).execute()\n    except Exception as e:\n        print(f"Log error: {e}")