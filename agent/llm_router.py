import os
import json
from groq import Groq

# Use Groq API instead of OpenRouter for fast, free interference
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "YOUR_GROQ_API_KEY_HERE")
client = Groq(api_key=GROQ_API_KEY)

DEFAULT_MODEL = "llama-3.3-70b-versatile"

def classify_intent_and_extract_keywords(user_message: str, chat_history: list, store_name: str = "المتجر", system_prompt_custom: str = None) -> dict:
    """
    Acts as the 'Traffic Cop'. Decides if we need clarifying questions or if we should search the DB.
    Returns a dict: {"action": "clarify" | "search" | "chat", "reply": "...", "keywords": ["..."]}
    """
    
    # Base system prompt with dynamic store name
    system_prompt = f"""
    أنت موظف مبيعات محترف ولبق جداً لدى "{store_name}". تتحدث بلهجة سعودية محترمة.
    
    مهمتك تحليل رسالة العميل وإخراج رد بصيغة JSON فقط، يحتوي على المفاتيح التالية:
    
    1. "action": 
       - اختر "search" بنسبة 90%: لأي سؤال عن المنتجات، توفرها، أسعارها، أو حتى طلبات عامة مثل (وش عندكم، أفضل منتجاتكم).
       - اختر "chat" بنسبة 10%: فقط لرسائل الترحيب والتحية الصافية جداً (مثل: هلا، السلام عليكم).
       
    2. "reply": 
       - إذا كان الخيار "chat"، اكتب رد ترحيبي لبق جداً (مثل: يا هلا بك في {store_name}، طال عمرك كيف أقدر أخدمك اليوم؟).
       - إذا كان الخيار "search" اتركه فارغاً "".
       
    3. "keywords": 
       - إذا كان "search"، استخرج الأسماء الجوهرية للبحث (مثل: حليب، عسل).
    """
    
    if system_prompt_custom:
        system_prompt += f"\n\nتعليمات إضافية خاصة بهذا النشاط:\n{system_prompt_custom}"
    
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

def generate_sales_reply(user_message: str, filtered_products: list, chat_history: list = None, store_name: str = "المتجر", system_prompt_custom: str = None) -> str:
    """
    Takes the filtered products and writes a human-like, persuasive Arabic message summarizing them.
    Incorporates full context and strict stock reporting rules.
    """
    
    base_prompt = f"""
    أنت بائع خبير ولبق في "{store_name}"، تتحدث بلهجة سعودية محترمة.
    النتائج المتوفرة من المخزن: {json.dumps(filtered_products, ensure_ascii=False)}
    
    أوامر الرد (طبقها بدقة واحترافية):
    1. عرض البيانات: تفحص حقل 'details' لكل منتج/خدمة. اعرض المعلومات الهامة للعميل (مثل السعر، النوع، المواصفات) بأسلوب جذاب ومرتب.
    2. المرونة: بما أن المتاجر تختلف، قد تجد معلومات مثل (المساحة، الموقع، مدة الخدمة، السعر). اشرحها للعميل وكأنك موظف خبير في هذا المجال تحديداً.
    3. قاعدة الكمية: إذا وجد حقل (stock) أو (الكمية) في الـ details وكان 0، أخبر العميل بنفاد الكمية.
    4. الأسلوب: استخدم لهجة سعودية ترحيبية (أبشر، سم، طال عمرك).
    5. الالتزام: لا تخترع معلومات غير موجودة في حقل الـ details المرفق.
    """
    
    if system_prompt_custom:
        base_prompt += f"\n\nتعليمات إضافية خاصة بهذا النشاط:\n{system_prompt_custom}"
        
    messages = [{"role": "system", "content": base_prompt}]
    
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
