import os
import json
import httpx
from database.db_client import get_supabase_client

async def get_ai_response(client_id: str, user_message: str, phone_number: str, channel: str = "unknown", image_base64: str = None, audio_base64: str = None, message_id: str = None) -> str:
    """
    يجلب إعدادات الذكاء الاصطناعي والبيانات ثم يولد رداً احترافياً (يدعم النصوص والصور والصوت)
    """
    supabase = get_supabase_client()

    # 1. جلب إعدادات الوكيل (الاسم والشركة)
    try:
        from merchant.planning.planning_config import get_planning_config
        from merchant.store_management.store_settings import get_store_settings
        
        settings = get_store_settings(client_id)
        company_name = settings.get("company_name", "الشركة")
        
        p = get_planning_config(client_id)
        # نستخدم المفاتيح التي تعود من get_planning_config وهي (ai_agent_name, ai_tone, business_description, store_activity)
        agent_name     = p.get("ai_agent_name") or company_name
        tone           = p.get("ai_tone") or "احترافي ومهذب"
        description    = p.get("business_description") or ""
        store_activity = p.get("store_activity") or ""
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
            if isinstance(ends_at_str, str):
                # تنظيف الصيغة إذا كانت تحتوي على أجزاء ثانية زائدة
                clean_date = ends_at_str.split('.')[0].replace('Z', '').replace(' ', 'T')
                ends_at = datetime.fromisoformat(clean_date)
                if ends_at < datetime.now():
                    return "عذراً، لقد انتهى اشتراك المتجر. يرجى التواصل مع الإدارة لتجديده."
        except Exception as e:
            print(f"Error parsing date '{ends_at_str}': {e}")
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
        # جلب إعدادات المزامنة
        sync_cfg = supabase.table("sync_config").select("*").eq("client_id", client_id).single().execute()
        
        # محاولة جلب البيانات اليدوية (إكسيل) كخيار أول أو احتياطي
        manual_res = supabase.table("merchant_manual_data").select("data").eq("client_id", client_id).execute()
        if manual_res.data:
            raw_data = manual_res.data[0]["data"]
            if isinstance(raw_data, list) and len(raw_data) > 0:
                columns = list(raw_data[0].keys())
                formatted_lines = [f"هيكل البيانات (الأعمدة المتاحة): {', '.join(columns)}"]
                formatted_lines.append("---")
                for item in raw_data[:300]:
                    line = " | ".join([f"{k}: {v}" for k, v in item.items()])
                    formatted_lines.append(f"- {line}")
                store_data = "\n".join(formatted_lines)
            else:
                store_data = json.dumps(raw_data, ensure_ascii=False)

        # إذا كانت المزامنة Aiven أو غيرها، يمكن إضافة منطقها هنا مستقبلاً
    except Exception as e:
        print(f"Warning: Could not fetch store data: {e}")

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

    # 3.6 جلب تدريب الأعمدة (Column Training)
    column_training_prompt = ""
    try:
        col_train_res = supabase.table("column_training").select("column_name, note, is_disabled").eq("client_id", client_id).execute()
        if col_train_res.data:
            train_notes = []
            for ct in col_train_res.data:
                status = "تجاهل هذا العمود تماماً ولا تذكره للعميل أبداً تحت أي ظرف" if ct['is_disabled'] else ct['note']
                train_notes.append(f"- العمود [{ct['column_name']}]: {status}")
            column_training_prompt = "\nتعليمات خاصة بأعمدة البيانات (يجب الالتزام بها حرفياً):\n" + "\n".join(train_notes) + "\n"
    except Exception as e:
        print(f"Warning: Could not fetch column training: {e}")

    # 3.7 جلب ذاكرة العميل (تاريخ المحادثات السابقة)
    chat_history_prompt = ""
    try:
        # جلب آخر 5 رسائل متبادلة مع هذا الرقم
        history_res = supabase.table("message_logs") \
            .select("message_text, ai_response, timestamp") \
            .order("timestamp", desc=True) \
            .eq("client_id", client_id) \
            .eq("phone_number", phone_number) \
            .limit(5) \
            .execute()
        
        if history_res.data:
            history = history_res.data[::-1]
            chat_history_prompt = "\nسياق المحادثة السابقة مع هذا العميل (للتذكر والمتابعة):\n"
            for h in history:
                chat_history_prompt += f"- العميل: {h['message_text']}\n"
                chat_history_prompt += f"- أنت: {h['ai_response']}\n"
            chat_history_prompt += "\nملاحظة: بما أن هناك تاريخ محادثة أعلاه (أكثر من رسالة)، فهذا يعني أنك قد رحبت بالعميل مسبقاً. التزم بالقاعدة رقم 2 في هويتك الشخصية ولا تكرر اسمك أو اسم المتجر الآن.\n"
    except Exception as e:
        print(f"Warning: Could not fetch chat history: {e}")

    # 4. بناء System Prompt
    product_context = ""
    if store_data:
        product_context = f"""
بيانات المنتجات والمخزون المتاحة حالياً:
-------------------------------------------
{store_data}
-------------------------------------------
{column_training_prompt}
ملاحظة هامة (القاعدة الذهبية): 
- استخدم البيانات أعلاه حصراً للإجابة عن الأسعار والمخزون.
- إذا لم تجد المنتج في القائمة أعلاه، لا تخترع سعراً أو تفاصيل أبداً. قل للعميل بلباقة: "عذراً، هذا المنتج غير متوفر حالياً في مخزوننا أو ربما تقصد شيئاً آخر؟"
- يمنع ذكر أي سعر أو معلومة لم تذكر في البيانات.
"""

    system_prompt = f"""هويتك الشخصية:
- اسمك هو "{agent_name}".
- قواعد التعريف بالنفس (صارمة جداً):
  1. إذا كانت هذه هي الرسالة الأولى في المحادثة (ترحيب)، يجب أن تعرف بنفسك وبالشركة: "مرحباً، أنا {agent_name} من {company_name}".
  2. إذا كان هناك تاريخ محادثة سابق (حتى لو رسالة واحدة فقط)، يمنع منعاً باتاً تكرار التعريف بنفسك أو بالمتجر. ادخل في صلب الموضوع مباشرة وكأنك تكمل المحادثة.
  3. كن طبيعياً ومختصراً؛ تحدث كبشر لا كآلة.

- نبرة صوتك (Tone): {tone}

{chat_history_prompt}

معلومات الشركة والخدمات العامة:
{description}

{product_context}

{business_rules_prompt}

قواعد صارمة جداً (دستور العمل):
1. الالتزام بالنشاط: نشاط المتجر الأساسي هو: [{store_activity}].
   - وظيفتك هي المساعدة في بيع المنتجات الموجودة في القائمة أعلاه.
   - يُمنع الإجابة على أسئلة خارج نطاق التجارة أو تخصص المتجر.
   - إذا سألك العميل عن شيء خارج النشاط تماماً، اعتذر بلطف وعد للموضوع التجاري.

2. منع المعلومات المضللة (الهلوسة):
   - لا تخترع منتجات غير موجودة.
   - اعتمد حصراً على قائمة المنتجات أعلاه والتعليمات الخاصة بالأعمدة للإجابة.
   - لا ترد على أسئلة سابقة تمت الإجابة عليها بالفعل في تاريخ المحادثة، ركز فقط على الرسالة الأخيرة للعميل.

3. الالتزام بتعليمات الأعمدة:
   - يجب عليك تطبيق جميع التعليمات المذكورة في "تعليمات خاصة بأعمدة البيانات" بدقة متناهية.
   - إذا كان العمود معطلاً (تجاهل هذا العمود تماماً)، لا تقم بذكر أو استخدام أي بيانات من هذا العمود للعميل نهائياً.

4. قواعد عامة وصارمة:
- رد دائماً بالعربية الفصحى أو بلهجة العميل إذا كانت عربية، أو بالإنجليزية إذا تحدث بها.
- يمنع منعاً باتاً استخدام أي رموز أو لغات غريبة في الرد.
- كن مقنعاً ومحترماً وركز على دفع العميل نحو "إتمام الطلب".
- الردود تكون مختصرة وجذابة (حد أقصى 3 فقرات).
- لا تذكر أنك ذكاء اصطناعي.
"""

    # 4. بناء الرسائل (دعم الرؤية Vision أو الصوت Native)
    # ملاحظة: حالياً فقط Google Gemini يدعم إرسال ملفات الصوت مباشرة عبر الـ API
    can_handle_audio = (provider == "google")
    
    if image_base64 or (audio_base64 and can_handle_audio):
        content_parts = []
        if user_message:
            content_parts.append({"type": "text", "text": user_message})
        elif image_base64:
            content_parts.append({"type": "text", "text": "وصلتني صورة، يرجى تحليلها والرد."})
        elif audio_base64:
            content_parts.append({"type": "text", "text": "استمع للمقطع الصوتي ونفذ المطلوب."})

        if image_base64:
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
            })
            
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content_parts}
        ]
    else:
        # إذا كان هناك صوت والنموذج لا يدعمه، ولم ننجح في التحويل لنص سابقاً
        final_msg = user_message
        if not final_msg and audio_base64:
            final_msg = "وصلتني رسالة صوتية تعذر تحويلها لنص. يرجى الاعتذار للعميل بلطف وطلب الكتابة نصياً."
            
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": final_msg}
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
            response = await _call_google(api_key, model_id, user_message, system_prompt, image_base64, audio_base64)
        elif provider == "openrouter":
            response = await _call_openrouter(api_key, model_id, messages)
        else:
            response = await _call_openai(api_key, model_id, messages)

        # 6. تسجيل السجل وتحديث العداد
        _log_message(supabase, client_id, user_message, response, phone_number, channel, message_id)
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
            json={"model": model_id, "messages": messages, "max_tokens": 500, "temperature": 0.1},
            timeout=30
        )
        data = res.json()
        if "choices" not in data:
            print(f"[OpenAI API Error] Response: {data}")
            return "عذراً، يبدو أن هناك ضغطاً على خوادم الذكاء الاصطناعي (OpenAI). يرجى المحاولة بعد قليل."
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
            json={"model": model_id, "system": system, "messages": user_messages, "max_tokens": 500, "temperature": 0.1},
            timeout=30
        )
        data = res.json()
        if "content" not in data:
            print(f"[Anthropic API Error] Response: {data}")
            return "عذراً، يبدو أن هناك ضغطاً على خوادم الذكاء الاصطناعي (Anthropic). يرجى المحاولة بعد قليل."
        return data["content"][0]["text"].strip()


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
            print(f"[Groq API Error] Response: {data}")
            return "عذراً، يبدو أن هناك ضغطاً على خوادم الذكاء الاصطناعي (Groq Rate Limit). يرجى المحاولة بعد قليل."
        return data["choices"][0]["message"]["content"].strip()


async def _call_google(api_key: str, model_id: str, user_message: str, system: str, image_base64: str = None, audio_base64: str = None) -> str:
    clean_model_id = model_id.strip().lower()
    clean_api_key = api_key.strip()
    
    if not clean_model_id.startswith("models/"):
        full_model_name = f"models/{clean_model_id}"
    else:
        full_model_name = clean_model_id
        
    url = f"https://generativelanguage.googleapis.com/v1beta/{full_model_name}:generateContent?key={clean_api_key}"
    headers = {"Content-Type": "application/json"}
    
    parts = []
    if user_message:
        parts.append({"text": user_message})
    elif image_base64:
        parts.append({"text": "ماذا ترى في هذه الصورة؟"})
    elif audio_base64:
        parts.append({"text": "استمع لهذا المقطع الصوتي ونفذ المطلوب منه في سياق المتجر."})

    if image_base64:
        parts.append({
            "inline_data": {
                "mime_type": "image/jpeg",
                "data": image_base64
            }
        })
    
    if audio_base64:
        parts.append({
            "inline_data": {
                "mime_type": "audio/ogg",
                "data": audio_base64
            }
        })

    body = {
        "systemInstruction": {
            "parts": [{"text": system}]
        },
        "contents": [
            {
                "role": "user",
                "parts": parts
            }
        ],
        "generationConfig": {"maxOutputTokens": 500, "temperature": 0.1}
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

async def _call_openrouter(api_key: str, model_id: str, messages: list) -> str:
    async with httpx.AsyncClient() as client:
        res = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://ai-sales-agent-dreu.onrender.com",
                "X-Title": "AI Sales Agent"
            },
            json={"model": model_id, "messages": messages, "max_tokens": 500, "temperature": 0.1},
            timeout=30
        )
        data = res.json()
        if "choices" in data:
            return data["choices"][0]["message"]["content"].strip()
        else:
            error_msg = data.get("error", {}).get("message", "Unknown OpenRouter error")
            print(f"[OpenRouter API Error] Response: {data}")
            return "عذراً، يبدو أن هناك ضغطاً على خوادم الذكاء الاصطناعي (OpenRouter). يرجى المحاولة بعد قليل."


def _log_message(supabase, client_id: str, user_message: str, ai_response: str, phone_number: str, channel: str = "whatsapp_evolution", message_id: str = None):
    try:
        supabase.table("message_logs").insert({
            "client_id": client_id,
            "channel": channel if channel != "unknown" else "whatsapp_evolution",
            "direction": "in",
            "phone_number": phone_number,
            "message_text": user_message,
            "ai_response": ai_response,
            "message_id": message_id
        }).execute()
    except Exception as e:
        print(f"Log error: {e}")
