import os
import json
from groq import Groq

# Use Groq API instead of OpenRouter for fast, free interference
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "YOUR_GROQ_API_KEY_HERE")
client = Groq(api_key=GROQ_API_KEY)

DEFAULT_MODEL = "llama-3.3-70b-versatile"

def classify_intent_and_extract_keywords(user_message: str, chat_history: list) -> dict:
    """
    Acts as the 'Traffic Cop'. Decides if we need clarifying questions or if we should search the DB.
    Returns a dict: {"action": "clarify" | "search" | "chat", "reply": "...", "keywords": ["..."]}
    """
    system_prompt = """
    أنت موظف مبيعات ذكي ومحترف، تتحدث باللهجة السعودية الودودة.
    مهمتك تحليل رسالة العميل وإخراج رد بصيغة JSON فقط، يحتوي على المفاتيح التالية:
    
    1. "action": 
       - اختر "chat" إذا كانت الرسالة ترحيبية أو سؤال عام (مثل: كيف الحال، سلام، من أنتم، شكرا، يعطيك العافية).
       - اختر "search" إذا كان العميل يسأل بوضوح عن توفر منتج أو سعره (مثل: بكم العطر؟، عندكم رز؟، تفاح).
       - اختر "clarify" إذا كان الطلب ناقصاً جداً ويحتاج توضيح لتتمكن من البحث عنه (مثل: أبغى شيء رخيص).
       
    2. "reply": 
       - إذا كان الخيار "chat" أو "clarify"، اكتب ردك الودود والمساعد للعميل هنا.
       - أما إذا كان الخيار "search" اتركه فارغاً "".
       
    3. "keywords": 
       - إذا كان الخيار "search"، استخرج أسماء المنتجات أو الكلمات المفتاحية كأسماء وحبات في قائمة (مثل: ["عطر", "ديور"]).
       - وإلا اتركها فارغة [].

    يجب أن يكون المخرج JSON صحيح 100% كما في هذا المثال:
    {"action": "chat", "reply": "يا هلا والله! كيف أقدر أخدمك اليوم؟", "keywords": []}
    """
    
    messages = [{"role": "system", "content": system_prompt}]
    
    # Safely inject history without causing alternating role constraint errors
    if chat_history:
        # Include previous user messages as an assistant context reminder
        context = "سياق رسائل العميل السابقة: " + " | ".join(chat_history[-4:])
        messages.append({"role": "assistant", "content": context})
        
    messages.append({"role": "user", "content": user_message})
    
    try:
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

def generate_sales_reply(user_message: str, filtered_products: list) -> str:
    """
    Takes the filtered products and writes a human-like, persuasive Arabic message summarizing them.
    """
    system_prompt = f"""
    أنت بائع سعودي محترف ونشمي. سأل العميل عن منتج، وهذه نتائج البحث في قاعدة البيانات لدينا:
    المنتجات المتوفرة: {json.dumps(filtered_products, ensure_ascii=False)}
    
    تعليمات هامة للرد:
    1. اكتب رداً للعميل بناءً على النتائج بلهجة سعودية ودودة واحترافية (مثل: أبشر، حياك الله، سم).
    2. استعرض الأسعار بوضوح مع ذكر (الوحدة/العبوة) إذا كانت متوفرة.
    3. إذا كانت (المنتجات المتوفرة) عبارة عن قائمة فارغة []، اعتذر للعميل بلطف وأخبره أن المنتج غير متوفر لدينا حالياً.
    4. إذا كان المنتج موجوداً ولكن (الكمية/stock) تساوي صفراً، أخبر العميل بلطف أن الكمية نفدت وسنقوم بتوفيرها قريباً.
    5. تحذير شديد: لا تخترع أسماء منتجات أو أسعار أو عروض من خارج القائمة نهائياً. التزم فقط بما هو متاح لك في المتوفر.
    """
    
    try:
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0.4
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"[-] Final Generation Error: {e}")
        return "المعذرة طال عمرك، صار فيه خطأ بسيط بالنظام. ممكن تعيد طلبك؟"
