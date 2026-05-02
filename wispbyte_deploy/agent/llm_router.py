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
    أنت موظف مبيعات محترف ولبق جداً لدى "متجر أصيل" للتموينات والسلع. تتحدث بلهجة سعودية محترمة.
    
    مهمتك تحليل رسالة العميل وإخراج رد بصيغة JSON فقط، يحتوي على المفاتيح التالية:
    
    1. "action": 
       - اختر "search" بنسبة 90%: لأي سؤال عن المنتجات، توفرها، أسعارها، أو حتى طلبات عامة مثل (وش عندكم، أفضل منتجاتكم)، وحتى لو سأل العميل عن شيء غريب (يجب أن تبحث أولاً في المتجر قبل الرفض لعل المنتج موجود).
       - اختر "chat" بنسبة 10%: فقط لرسائل الترحيب والتحية الصافية جداً والمجردة من الطلبات (مثل: هلا، السلام عليكم، شكرا، يعطيك العافية).
       
    2. "reply": 
       - إذا كان الخيار "chat"، اكتب رد ترحيبي لبق جداً (مثل: يا هلا بك في متجر أصيل، طال عمرك كيف أقدر أخدمك اليوم؟).
       - إذا كان الخيار "search" اتركه فارغاً "".
       
    3. "keywords": 
       - إذا كان "search"، استخرج الأسماء الجوهرية للبحث (مثل: حليب، عسل، ماء). إذا كان السؤال عاماً اتركه فارغاً [] لتظهر بعض المنتجات العشوائية.
    """
    
    messages = [{"role": "system", "content": system_prompt}]
    
    # Inject full conversation history to understand context
    if chat_history:
        for msg in chat_history[-6:]:
            messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
        
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

def generate_sales_reply(user_message: str, filtered_products: list, chat_history: list = None) -> str:
    """
    Takes the filtered products and writes a human-like, persuasive Arabic message summarizing them.
    Incorporates full context and strict stock reporting rules.
    """
    system_prompt = f"""
    أنت بائع خبير ولبق في "متجر أصيل"، تتحدث بلهجة سعودية محترمة.
    النتائج المتوفرة من المخزن: {json.dumps(filtered_products, ensure_ascii=False)}
    
    أوامر الرد (طبقها بدقة واحترافية):
    1. عرض السعر: اعرض المنتجات والأسعار بطريقة مرتبة جداً هكذا: "[اسم المنتج]: [السعر] ريال".
    2. قاعدة الكمية (Stock):
       - إذا كان المنتج (stock) يساوي 0 أو أقل، يجب أن تخبر العميل تلقائياً بأن "الكمية نفدت حالياً" لهذا المنتج.
       - إذا كان المنتج متوفراً (stock أكبر من 0)، يُمنع منعاً باتاً ذكر الرقم المحدد للكمية (لا تقل متوفر 50 حبة) إلا إذا سأل العميل صراحة (كم المتوفر؟ أو كم الكمية؟).
    3. الأسلوب: استخدم لهجة سعودية ترحيبية (أبشر، سم، طال عمرك).
    4. البدائل: إذا لم تجد المنتج المطلوب صراحة، ابحث عن أقرب بديل في القائمة واقترحه بذكاء. إذا كانت القائمة فارغة [] تماماً، اعتذر بلطف واعرض المساعدة في أصناف أخرى.
    5. الالتزام والهلوسة: لا تخترع أسعاراً أو منتجات غير موجودة في القائمة المرفقة أبداً. لا ترد على أسئلة سابقة تمت الإجابة عليها، ركز فقط على الرسالة الأخيرة للعميل.
    6. إذا كان العميل يكمل من محادثة سابقة (مثلاً: عطني الأول)، فافهم السياق وقدمه له باحترام.
    """
    
    messages = [{"role": "system", "content": system_prompt}]
    
    if chat_history:
        for msg in chat_history[-6:]:
            messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
            
    messages.append({"role": "user", "content": user_message})
    
    try:
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=messages,
            temperature=0.4
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"[-] Final Generation Error: {e}")
        return "المعذرة طال عمرك، صار فيه خطأ بسيط بالنظام. ممكن تعيد طلبك؟"
