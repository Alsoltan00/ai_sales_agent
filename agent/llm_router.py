import os
import json
from groq import Groq

# Use Groq API instead of OpenRouter for fast, free inference
def _get_groq_client():
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if api_key and api_key != "YOUR_GROQ_API_KEY_HERE":
        try:
            return Groq(api_key=api_key)
        except Exception:
            pass
    return None

DEFAULT_MODEL = "llama-3.3-70b-versatile"

def classify_intent_and_extract_keywords(user_message: str, chat_history: list, store_name: str = "المتجر", store_id: str = None, system_prompt_custom: str = None) -> dict:
    """
    Acts as the 'Traffic Cop'. Decides if we need clarifying questions or if we should search the DB.
    Returns a dict: {"action": "clarify" | "search" | "chat", "reply": "...", "keywords": ["..."]}
    """
    
    # Base system prompt with dynamic store name
    system_prompt = f"""
    أنت موظف مبيعات محترف ولبق جداً لدى "{store_name}". تتحدث بلهجة سعودية محترمة.
    
    مهمتك تحليل رسالة العميل (مع فهم سياق المحادثة السابقة بدقة شديدة) وإخراج رد بصيغة JSON صالحة فقط، حسب القواعد التالية:
    
    1. "action": 
       - "search": للأسئلة عن منتجات للبحث عنها (مثل: وش عندكم عطور، هل متوفر سيروم الوجه؟).
       - "chat": إذا كان العميل يكمل طلباً أو يختار من منتجات عرضتها له للتو (مثل: "أبي رقم 1"، "هت لي 5"، "هذا اسمي وعنواني").
       
    2. "reply": 
       - إذا كان الخيار "chat"، اكتب ردك لعميلك مباشرة بلهجة سعودية هنا. إذا طلب كمية، أكد له الطلب من المحادثة السابقة واطلب بياناته (مثال: "أبشر طال عمرك، جهزت لك 5 حبات من السيروم، عطني اسمك ورقم الجوال عشان نعتمد طلبك").
       - إذا "search"، اتركه فارغاً "".
       
    3. "keywords": 
       - إذا "search"، ضع هنا كلمة البحث (مثل: ["سيروم"]). إذا "chat"، دعه فارغاً [].

    مثال للإخراج المطلوب (عليك الالتزام بهذا التنسيق الحرفي JSON):
    {{
        "action": "chat",
        "reply": "أبشر، جهزت لك 5 حبات من السيروم اللي طلبته. عطني تفاصيلك للطلب.",
        "keywords": []
    }}
    """
    
    if system_prompt_custom:
        try:
            # Try to parse it as JSON if it came from the new advanced UI
            ai_settings = json.loads(system_prompt_custom)
            system_prompt += f"\n\nمعلومات عن المتجر ({store_name}):\n{ai_settings.get('about', '')}"
            system_prompt += f"\n\nأسلوب التحدث المطلوب:\n{ai_settings.get('tone', '')}"
            if ai_settings.get('policy'):
                system_prompt += f"\n\nسياسة المتجر:\n{ai_settings.get('policy')}"
            if ai_settings.get('faq'):
                system_prompt += f"\n\nالأسئلة الشائعة:\n{ai_settings.get('faq')}"
        except:
            # Fallback to plain text for older stores
            system_prompt += f"\n\nتعليمات إضافية خاصة بهذا النشاط:\n{system_prompt_custom}"
            
    # Inject Dynamic Columns context
    from agent.database import get_store_columns
    store_cols = get_store_columns(store_id)
    if store_cols:
        system_prompt += f"\n\nالأعمدة المتاحة في قاعدة البيانات للإجابة على العميل: [{', '.join(store_cols)}]"
    
    messages = [{"role": "system", "content": system_prompt}]
    
    # Inject full conversation history to understand context
    if chat_history:
        for msg in chat_history[-6:]:
            messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
        
    messages.append({"role": "user", "content": user_message})
    
    try:
        client = _get_groq_client()
        if not client:
            return {"action": "search", "reply": "", "keywords": [user_message]}
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=messages,
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content
        return json.loads(content)
    except Exception as e:
        print(f"[-] Intent Classification Error: {e}")
        # Default fallback to search with the whole message as keyword
        return {"action": "search", "reply": "", "keywords": [user_message]}

def generate_sales_reply(user_message: str, filtered_products: list, chat_history: list = None, store_name: str = "المتجر", system_prompt_custom: str = None) -> str:
    """
    Takes the filtered products and writes a human-like, persuasive Arabic message summarizing them.
    Incorporates full context and strict stock reporting rules.
    """
    
    base_prompt = f"""
    أنت بائع خبير ولبق في "{store_name}"، تتحدث بلهجة سعودية محترمة.
    بناءً على طلب العميل الأخير، هذه هي النتيجة الحية من المخزن: {json.dumps(filtered_products, ensure_ascii=False)}
    
    أوامر الرد (طبقها بدقة واحترافية):
    1. الاستمرارية والسياق: اقرأ المحادثة السابقة بدقة! إذا كان العميل يطلب كمية لمنتج تحدثتم عنه للتو (مثل قوله: "أعطني 5 حبات من المقاوم للتجعيد")، إياك أن تعرض المنتج وكأنه جديد أو تذكر الباركود بشكل آلي! بل تأكد من توفر الكمية في النتيجة أعلاه، ثم رد بشكل متصل وطبيعي: "أبشر طال عمرك، الـ 5 حبات متوفرة ومحجوزة لك من السيروم المقاوم للتجعيد. عشان نعتمد الطلب، أحتاج الاسم ورقم الجوال."
    2. عرض البيانات: فقط إذا كان العميل يسأل أو يستفسر لأول مرة، قم بعرض المنتجات بأسلوب جذاب ومرتب واذكر السعر.
    3. قاعدة الكمية: إذا كانت الكمية (stock) المطلوبة غير متوفرة أو صفر، اعتذر بلباقة وأخبره بالكمية المتبقية.
    4. الأسلوب: لبق، مرحب (أبشر، سم)، والأهم أن يكون طبيعياً كالبشر ولا يبدو كآلة سرد بيانات.
    5. الالتزام المطلق: لا تخترع أسعاراً أو منتجات أو كميات غير موجودة في النتيجة أعلاه.
    """
    
    if system_prompt_custom:
        base_prompt += f"\n\nتعليمات إضافية خاصة بهذا النشاط:\n{system_prompt_custom}"
        
    messages = [{"role": "system", "content": base_prompt}]
    
    if chat_history:
        for msg in chat_history[-6:]:
            messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
            
    messages.append({"role": "user", "content": user_message})
    
    try:
        client = _get_groq_client()
        if not client:
            return "المعذرة طال عمرك، النظام يحتاج إعداد مفتاح الذكاء الاصطناعي."
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=messages,
            temperature=0.4
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"[-] Final Generation Error: {e}")
        return "المعذرة طال عمرك، صار فيه خطأ بسيط بالنظام. ممكن تعيد طلبك؟"
