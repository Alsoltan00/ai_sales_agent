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

    # 2. جلب إعدادات النموذج النشط من خلال باقة العميل والتحقق من رصيد الرسائل
    try:
        # 1. جلب بيانات الاشتراك من جدول العملاء (العميل)
        client_sub_res = supabase.table("clients").select("subscription_plan, subscription_ends_at, status, messages_used").eq("id", client_id).single().execute()
        
        if not client_sub_res.data:
            return "عذراً، المتجر ليس لديه حساب نشط."
            
        sub_data = client_sub_res.data
        if sub_data.get("status") != "active":
            return "عذراً، المتجر غير نشط. يرجى التواصل مع الإدارة."
            
        from datetime import datetime
        ends_at_str = sub_data.get("subscription_ends_at")
        if not ends_at_str:
            return "عذراً، المتجر ليس لديه اشتراك نشط. يرجى التواصل مع الإدارة."
            
        try:
            ends_at = datetime.fromisoformat(ends_at_str.replace('Z', '+00:00'))
            if ends_at < datetime.now(ends_at.tzinfo):
                return "عذراً، لقد انتهى اشتراك المتجر. يرجى التواصل مع الإدارة لتجديده."
        except Exception as e:
            print(f"Error parsing date: {e}")
            pass
            
        client_plan = sub_data.get("subscription_plan", "free")
        messages_used = sub_data.get("messages_used", 0)

        # 2. جلب إعدادات الباقة (الخطة)
        plan_res = supabase.table("subscription_plans").select("permissions").eq("name", client_plan).execute()
        if not plan_res.data:
            return "عذراً، إعدادات باقة المتجر غير صالحة."
        
        import json
        perms = plan_res.data[0].get("permissions", {})
        if isinstance(perms, str):
            try: perms = json.loads(perms)
            except: perms = {}

        # 3. التحقق من رصيد الرسائل المتبقي
        max_messages = perms.get("max_messages", 0)
        if max_messages > 0 and messages_used >= max_messages:
            return "عفواً، لقد استنفد المتجر رصيد الرسائل المخصص لباقته. يرجى التواصل مع الإدارة لشحن الرصيد لتتمكن من المتابعة."

        # 4. جلب نموذج الذكاء المخصص للباقة من المكتبة العالمية
        assigned_model_id = perms.get("assigned_model_id")
        if not assigned_model_id:
            return "عذراً، لم يتم تخصيص نموذج ذكاء اصطناعي لهذه الباقة. يرجى مراجعة الإدارة."

        model_res = supabase.table("global_ai_models").select("*").eq("id", assigned_model_id).execute()
        if not model_res.data:
            return "عذراً، نموذج الذكاء الاصطناعي المخصص غير متوفر حالياً."

        ai_cfg_data = model_res.data[0]
        
    except Exception as e:
        print(f"Error fetching AI config: {e}")
        ai_cfg_data = None

    if not ai_cfg_data:
        return "عذراً، حدث خطأ أثناء إعداد الذكاء الاصطناعي. يرجى المحاولة لاحقاً."

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

    # 3.5 جلب قواعد العمل (Business Rules)
    business_rules_prompt = ""
    try:
        rules_res = supabase.table("business_rules").select("rules_data").eq("client_id", client_id).single().execute()
        if rules_res.data and rules_res.data.get("rules_data"):
            rd = rules_res.data["rules_data"]
            business_rules_prompt = f"""
دستور عمل وقواعد العمل (يجب الالتزام بها قطعيًا):
- سياسة الخصم: {rd.get('discount_type', 'حسب الحاجة')}. {rd.get('discount_msg', '')}
- الشحن: {rd.get('shipping_type', 'حسب السياسة')}. {rd.get('shipping_msg', '')}
- الدفع: {rd.get('payment_type', 'متاح بكافة الوسائل')}.
- عند نفاذ المخزون: {rd.get('stock_out_type', 'الاعتذار')}. {rd.get('stock_out_msg', '')}
- معلومات إضافية للمنتجات: {rd.get('details_missing_type', '')}. {rd.get('details_static_info', '')}
- نبرة الصوت: {rd.get('tone_type', tone)}. {rd.get('complaint_msg', '')}
- خارج أوقات العمل: {rd.get('afterhours_type', 'الرد غداً')}.
- إتمام البيع: {rd.get('checkout_type', 'رابط مباشر')}.
- حواجز الحماية: يمنع منعاً باتاً الحديث في: { 'مقارنة الأسعار، ' if rd.get('ban_prices') else '' }{ 'مواعيد وصول دقيقة، ' if rd.get('ban_eta') else '' }{rd.get('ban_custom', '')}
- سياسة المكاسرة: {rd.get('bargain_type', 'ممنوعة')}.
"""
    except Exception as e:
        print(f"Warning: Could not fetch business rules: {e}")

    # 4. بناء System Prompt
    system_prompt = f"""أنت {agent_name}، مندوب مبيعات ذكي يعمل لدى {company_name}.

لهجة الرد: {tone}

معلومات الشركة والخدمات:
{description}

{f"بيانات المنتجات والمخزون الحالي (JSON):{chr(10)}{store_data}" if store_data else ""}

{business_rules_prompt}

قواعد عامة إضافية:
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

        # 6. تسجيل السجل وتحديث العداد
        _log_message(supabase, client_id, user_message, response, phone_number, channel)
        try:
            supabase.table("clients").update({"messages_used": messages_used + 1}).eq("id", client_id).execute()
        except Exception as update_err:
            print(f"Error updating messages count: {update_err}")
            
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
