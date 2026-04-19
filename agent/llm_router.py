import os
import json
from groq import Groq

# Use Groq API instead of OpenRouter for fast, free inference
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "YOUR_GROQ_API_KEY_HERE")
client = Groq(api_key=GROQ_API_KEY)

DEFAULT_MODEL = "llama-3.1-8b-instant"

def classify_intent_and_extract_keywords(user_message: str, chat_history: list) -> dict:
    """
    Acts as the 'Traffic Cop'. Decides if we need clarifying questions or if we should search the DB.
    Returns a dict: {"action": "clarify" | "search", "reply": "...", "keywords": ["..."]}
    """
    system_prompt = """
    أنت مدير مبيعات ذكي. مهمتك تحليل طلب العميل وتقرير الخطوة التالية:
    1. إذا كان الطلب غير واضح أو عام جداً (مثل: "عندكم عروض؟" أو "أبغى كريم" أو كلمة للترحيب مثل "سلام" أو "كيف الحال"): 
       يجب أن تطلب توضيحاً بلطف لتحديد المنتج بدقة أو ترحب به وتخبره بخدماتك.
       الرد بصيغة JSON: {"action": "clarify", "reply": "ردك هنا", "keywords": []}
       
    2. إذا كان الطلب واضحاً ومحدداً لمنتجات (مثل: "بكم عطر ديور؟" أو "أبغى أرز بسمتي"):
       استخرج الكلمات المفتاحية الأساسية للبحث.
       الرد بصيغة JSON: {"action": "search", "reply": "", "keywords": ["عطر", "ديور"]}
       
    يجب أن يكون ردك حصرياً بصيغة JSON قابلة للقراءة البرمجية فقط.
    """
    
    messages = [{"role": "system", "content": system_prompt}]
    
    # Safely inject history without causing alternating role constraint errors
    if chat_history:
        # Include previous user messages as an assistant context reminder
        context = "الرسائل السابقة للعميل للتذكير: " + " | ".join(chat_history[-3:])
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
    أنت بائع سعودي محترف ونشمي. تم جلب هذه المنتجات للعميل من قاعدة بيانات المتجر:
    {json.dumps(filtered_products, ensure_ascii=False)}
    
    تعليمات هامة للرد:
    1. اكتب رداً تسويقياً للعميل بناءً على طلبه بلهجة ودودة واحترافية.
    2. استخدم تفاصيل (الوحدة والعبوة) إذا كانت متوفرة ليكون الرد دقيقاً.
    3. إذا كان المنتج (الكمية المتوفرة/stock) صفراً أو غير متوفر، أخبر العميل بلطف أنه غير متوفر حالياً.
    4. استعرض الأسعار بوضوح ولا تنشئ أي معلومات من خارج القائمة.
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
