import os
import json
import httpx
from database.db_client import get_supabase_client

async def get_ai_response(client_id: str, phone_number: str, user_message: str, 
                         image_base64: str = None, audio_base64: str = None, 
                         message_id: str = None, channel: str = "whatsapp"):
    """
    High-Precision AI Engine v3.0 (Dashboard-Synced)
    Fully aligned with Merchant Dashboard interfaces.
    """
    supabase = get_supabase_client()
    
    # 1. PRIMARY DATA FETCH (Store Identity)
    client_res = supabase.table("clients").select("*").eq("id", client_id).single().execute()
    if not client_res.data: return "عذراً، المتجر غير موجود."
    
    c = client_res.data
    agent_name = c.get("agent_name", "نوره")
    company_name = c.get("company_name", "متجر أصيل")
    store_activity = c.get("store_activity", "تجارة")
    description = c.get("description", "")
    base_tone = c.get("ai_tone", "حماسي وتسويقي")

    # 2. MODEL RESOLUTION (Plan vs Config)
    api_key, model_id, provider = None, "gpt-3.5-turbo", "openai"
    try:
        plan_res = supabase.table("clients").select("subscription_plan").eq("id", client_id).single().execute()
        if plan_res.data:
            p_name = plan_res.data["subscription_plan"]
            p_det = supabase.table("subscription_plans").select("permissions").eq("name", p_name).single().execute()
            if p_det.data:
                perms = p_det.data.get("permissions", {})
                if isinstance(perms, str): perms = json.loads(perms)
                mid = perms.get("assigned_model_id")
                if mid:
                    gm = supabase.table("global_ai_models").select("*").eq("id", mid).single().execute()
                    if gm.data:
                        api_key, model_id, provider = gm.data["api_key"], gm.data["model_id"], gm.data["provider"].lower()

        if not api_key:
            m_cfg = supabase.table("ai_models_config").select("*").eq("client_id", client_id).eq("is_active", True).execute()
            if m_cfg.data:
                api_key, model_id, provider = m_cfg.data[0]["api_key"], m_cfg.data[0]["model_id"], m_cfg.data[0]["provider"].lower()
    except Exception: pass

    if c.get("messages_used", 0) >= c.get("message_limit", 1000):
        return "انتهى رصيد الرسائل للمتجر."

    # 3. COLUMN TRAINING (High Precision Dictionary)
    col_dict = ""
    try:
        col_res = supabase.table("column_training").select("column_name, note").eq("client_id", client_id).execute()
        if col_res.data:
            col_dict = "\n".join([f"- **{i['column_name']}**: {i['note']}" for i in col_res.data])
    except Exception: pass

    # 4. MERCHANT MANUAL DATA (Smart Product Search)
    product_data = ""
    try:
        data_res = supabase.table("merchant_manual_data").select("data").eq("client_id", client_id).execute()
        if data_res.data and data_res.data[0].get("data"):
            all_rows = data_res.data[0]["data"]
            
            # Smart Filtering: Find products that match keywords in the user message
            keywords = [k.strip() for k in user_message.lower().split() if len(k) > 2]
            matched_rows = []
            
            if keywords:
                for r in all_rows:
                    r_text = " ".join([str(v).lower() for v in r.values()]).lower()
                    if any(kw in r_text for kw in keywords):
                        matched_rows.append(r)
            
            # Combine matched rows + some general rows for variety
            final_rows = matched_rows[:40] # Priority to matches
            if len(final_rows) < 20:
                # Add some non-matched rows to fill the context
                remaining = [r for r in all_rows if r not in final_rows]
                final_rows.extend(remaining[:(20 - len(final_rows))])
            
            items_list = []
            for r in final_rows:
                # Skip technical columns (long digits)
                clean_r = {k: v for k, v in r.items() if not str(v).isdigit() or len(str(v)) < 12}
                items_list.append(" | ".join([f"{k}: {v}" for k, v in clean_r.items()]))
            
            product_data = "\n".join([f"• {l}" for l in items_list])
            if matched_rows:
                product_data = f"تم العثور على نتائج مطابقة لطلبك:\n{product_data}"
    except Exception as e:
        print(f"Warning: Data fetch failed: {e}")

    # 5. BUSINESS RULES (Operational Logic)
    rules_prompt = ""
    try:
        r_res = supabase.table("business_rules").select("rules_data").eq("client_id", client_id).single().execute()
        if r_res.data:
            rd = r_res.data["rules_data"]
            checkout = "إتمام الطلب يدوياً داخل المحادثة." if rd.get("checkout_type") == "chat" else "توجيه العميل للمتجر الإلكتروني."
            payments = []
            if rd.get("chat_payment_cod"): payments.append("الدفع عند الاستلام")
            if rd.get("chat_payment_transfer"): payments.append(f"تحويل بنكي ({rd.get('bank_accounts','')})")
            
            rules_prompt = f"""
### دستور العمل (يجب الالتزام به):
1. **مسار الطلب:** {checkout}
2. **طرق الدفع:** {', '.join(payments) if payments else 'حسب الاتفاق'}.
3. **الخصومات:** {rd.get('discount_msg', 'لا توجد خصومات حالية')}.
4. **الشكاوى:** {rd.get('complaint_msg', 'سيتم التصعيد للإدارة')}.
"""
    except Exception: pass

    # 6. ULTIMATE SYSTEM PROMPT
    final_prompt = f"""# الهوية المهنية
أنت "{agent_name}"، موظف مبيعات محترف في "{company_name}".
نشاط المتجر: {store_activity}.
نبرة الصوت المطلوبة: {base_tone}.

# دليل البيانات (قاموس الأعمدة)
{col_dict}

# المنتجات المتوفرة (المصدر الرسمي)
{product_data if product_data else "يتم تحديث القائمة حالياً، اعتذر للعميل."}

{rules_prompt}

# قوانين المبيعات الصارمة:
- **الثقة والدقة:** لا تبع منتجاً غير موجود في القائمة أعلاه. إذا لم تجد الصنف، قل للعميل "غير متوفر حالياً".
- **الذكاء الاجتماعي:** ممنوع ذكر أي أمور تقنية (رقم الجوال، قاعدة البيانات، استلام الرقم). تحدث كإنسان.
- **إغلاق البيع:** إذا طلب العميل منتجاً، شجعه وأكد له الجودة، ثم اطلب بياناته (الاسم، العنوان) لإتمام الطلب يدوياً.
- **تفسير الإشارات:** إذا قال العميل "هذا" أو "الأول"، راجع فوراً آخر منتج ذكرته أنت في ردك السابق.
"""

    # 7. HISTORY & EXECUTION
    history = []
    search_phone = phone_number.split("@")[0]
    try:
        h = supabase.table("message_logs").select("message_text, ai_response").or_(f"phone_number.eq.{search_phone},phone_number.eq.{phone_number}").eq("client_id", client_id).order("timestamp", desc=True).limit(8).execute()
        if h.data:
            for m in reversed(h.data):
                if m.get("message_text"): history.append({"role": "user", "content": m["message_text"]})
                if m.get("ai_response"): history.append({"role": "assistant", "content": m["ai_response"]})
    except Exception: pass

    messages = [{"role": "system", "content": final_prompt}]
    messages.extend(history)
    
    if image_base64:
        messages.append({"role": "user", "content": [{"type": "text", "text": user_message or "حلل الصورة"}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}]})
    else:
        messages.append({"role": "user", "content": user_message})

    # Call LLM based on provider
    try:
        if provider == "openai": res = await _call_openai(api_key, model_id, messages)
        elif provider == "google": res = await _call_google(api_key, model_id, messages, final_prompt)
        elif provider == "openrouter": res = await _call_openrouter(api_key, model_id, messages)
        else: res = await _call_openrouter(api_key, model_id, messages)

        _log_message(supabase, client_id, user_message, res, phone_number, channel, message_id)
        supabase.table("clients").update({"messages_used": c.get("messages_used",0)+1}).eq("id", client_id).execute()
        return res
    except Exception as e:
        return f"عذراً، حدث خطأ تقني في الاتصال بمزود الذكاء ({provider})."

# Helper Functions (Keep original implementations but optimize for speed)
async def _call_openai(api_key, model, msgs):
    async with httpx.AsyncClient() as c:
        r = await c.post("https://api.openai.com/v1/chat/completions", headers={"Authorization": f"Bearer {api_key}"}, json={"model": model, "messages": msgs, "temperature": 0.1}, timeout=30)
        return r.json()["choices"][0]["message"]["content"].strip()

async def _call_google(api_key, model, msgs, system):
    m_id = model.strip() if model.startswith("models/") else f"models/{model.strip()}"
    url = f"https://generativelanguage.googleapis.com/v1beta/{m_id}:generateContent?key={api_key}"
    contents = []
    for m in msgs:
        if m["role"] == "system": continue
        role = "user" if m["role"] == "user" else "model"
        parts = [{"text": m["content"]}] if isinstance(m["content"], str) else []
        if isinstance(m["content"], list):
            for p in m["content"]:
                if p["type"] == "text": parts.append({"text": p["text"]})
                elif p["type"] == "image_url": parts.append({"inline_data": {"mime_type": "image/jpeg", "data": p["image_url"]["url"].split(",")[-1]}})
        contents.append({"role": role, "parts": parts})
    body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents, "generationConfig": {"temperature": 0.1}}
    async with httpx.AsyncClient() as c:
        r = await c.post(url, json=body, timeout=30)
        return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()

async def _call_openrouter(api_key, model, msgs):
    async with httpx.AsyncClient() as c:
        r = await c.post("https://openrouter.ai/api/v1/chat/completions", headers={"Authorization": f"Bearer {api_key}"}, json={"model": model, "messages": msgs}, timeout=30)
        return r.json()["choices"][0]["message"]["content"].strip()

def _log_message(supabase, client_id, user_msg, ai_res, phone, channel, msg_id):
    try:
        supabase.table("message_logs").insert({"client_id": client_id, "phone_number": phone, "message_text": user_msg, "ai_response": ai_res, "channel": channel, "message_id": msg_id}).execute()
    except Exception: pass