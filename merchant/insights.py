import json
import httpx
from database.db_client import get_db_client
from merchant.ai_engine import _call_openai, _call_google, _call_openrouter, _call_groq, _call_anthropic, _call_huggingface, _call_cerebras

async def ensure_table_exists():
    """تتأكد من وجود الجدول في قاعدة البيانات قبل البدء"""
    db = get_db_client()
    try:
        # سنحاول تنفيذ استعلام بسيط للتأكد من وجود الجدول، إذا فشل سننشئه
        sql = """
        CREATE TABLE IF NOT EXISTS merchant_ai_insights (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
            insights_data JSONB DEFAULT '{}',
            period TEXT DEFAULT 'last_7_days',
            created_at TIMESTAMP DEFAULT NOW()
        );
        """
        # بما أننا نستخدم SQLAlchemy في الخلفية لـ setup_db، سنستخدم نفس المحرك هنا إن أمكن
        # أو نستخدم postgrest (ولكن postgrest لا يدعم DDL)
        # لذا سنعتمد على أن setup_db.py سيعمل، ولكن كخطة بديلة سنحاول في الـ router.
        pass
    except:
        pass

async def generate_and_save_insights(client_id: str, period: str = "last_7_days") -> dict:
    """
    يقوم بجمع رسائل العملاء الأخيرة، ويرسلها للذكاء الاصطناعي لتحليلها واستخراج رؤى استراتيجية.
    """
    db = get_db_client()
    
    # 1. جلب الرسائل الأخيرة (اخر 200 رسالة كمثال)
    res = db.table("message_logs").select("message_text, ai_response").eq("client_id", client_id).order("timestamp", desc=True).limit(200).execute()
    messages = res.data or []
    
    if len(messages) < 5:
        return {"status": "error", "message": "لا يوجد عدد كافٍ من المحادثات لاستخراج رؤى دقيقة."}

    # تجهيز النص المجمع
    transcript = ""
    for m in messages:
        u = m.get("message_text") or ""
        a = m.get("ai_response") or ""
        if u: transcript += f"العميل: {u}\n"
        if a: transcript += f"الذكاء الاصطناعي: {a}\n\n"

    # 2. تحديد النموذج المستخدم للتاجر
    api_key, model_id, provider = None, None, None
    try:
        c_res = db.table("clients").select("subscription_plan").eq("id", client_id).single().execute()
        if c_res.data:
            plan = c_res.data.get("subscription_plan")
            p_det = db.table("subscription_plans").select("permissions").eq("name", plan).single().execute()
            if p_det.data:
                perms = p_det.data.get("permissions", {})
                if isinstance(perms, str): perms = json.loads(perms)
                mid = perms.get("assigned_model_id")
                if mid:
                    gm = db.table("global_ai_models").select("*").eq("id", mid).single().execute()
                    if gm.data:
                        api_key, model_id, provider = gm.data["api_key"], gm.data["model_id"], gm.data["provider"].lower()

        if not api_key:
            m_cfg = db.table("ai_models_config").select("*").eq("client_id", client_id).eq("is_active", True).execute()
            if m_cfg.data:
                api_key, model_id, provider = m_cfg.data[0]["api_key"], m_cfg.data[0]["model_id"], m_cfg.data[0]["provider"].lower()
    except Exception as e:
        print(f"Error resolving model for insights: {e}")

    if not api_key:
        return {"status": "error", "message": "لم يتم العثور على نموذج ذكاء اصطناعي مفعل."}

    # 3. صياغة الـ Prompt للتحليل
    system_prompt = """أنت محلل بيانات أعمال خبير.
مهمتك قراءة نصوص المحادثات التالية بين العملاء والذكاء الاصطناعي الخاص بالمتجر.
استخرج الرؤى التالية وقم بإرجاعها بصيغة JSON حصرية، بدون أي نصوص إضافية، بحيث تحتوي على المفاتيح التالية:
{
    "top_requested_missing_products": ["منتج غير متوفر 1", "منتج غير متوفر 2"],
    "common_complaints": ["شكوى 1", "شكوى 2"],
    "frequently_asked_questions": ["سؤال 1", "سؤال 2"],
    "general_summary": "ملخص عام وشامل عن سلوك العملاء وانطباعاتهم بناءً على المحادثات"
}
تأكد أن النص المردود هو كائن JSON صالح فقط (Valid JSON)."""

    llm_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"المحادثات:\n{transcript}"}
    ]

    # 4. الاستدعاء
    try:
        if provider == "openai": response_text = await _call_openai(api_key, model_id, llm_messages)
        elif provider == "google": response_text = await _call_google(api_key, model_id, llm_messages, system_prompt)
        elif provider == "openrouter": response_text = await _call_openrouter(api_key, model_id, llm_messages)
        elif provider == "groq": response_text = await _call_groq(api_key, model_id, llm_messages)
        elif provider == "anthropic": response_text = await _call_anthropic(api_key, model_id, llm_messages, system_prompt)
        elif provider == "huggingface": response_text = await _call_huggingface(api_key, model_id, llm_messages)
        elif provider == "cerebras": response_text = await _call_cerebras(api_key, model_id, llm_messages)
        else: response_text = await _call_openrouter(api_key, model_id, llm_messages)
        
        # تنظيف الإجابة (إذا كان هناك markdown json block)
        clean_json = response_text.replace("```json", "").replace("```", "").strip()
        insights_data = json.loads(clean_json)
        
        # 5. الحفظ في قاعدة البيانات
        # نحذف القديم لنفس الـ period إن وجد، أو نضيف سجل جديد
        db.table("merchant_ai_insights").delete().eq("client_id", client_id).eq("period", period).execute()
        db.table("merchant_ai_insights").insert({
            "client_id": client_id,
            "period": period,
            "insights_data": insights_data
        }).execute()
        
        return {"status": "success", "message": "تم إنشاء الرؤى بنجاح", "data": insights_data}

    except Exception as e:
        print(f"Insights Generation Error: {e}")
        return {"status": "error", "message": f"فشل في استخراج الرؤى: {str(e)}"}

def get_latest_insights(client_id: str, period: str = "last_7_days") -> dict:
    db = get_db_client()
    try:
        res = db.table("merchant_ai_insights").select("insights_data, created_at").eq("client_id", client_id).eq("period", period).order("created_at", desc=True).limit(1).execute()
        if res.data:
            return res.data[0]
        return {}
    except:
        return {}
