import os
import requests
import json

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "YOUR_OPENROUTER_API_KEY_HERE")
# Using a strong open-source model available on OpenRouter as default
DEFAULT_MODEL = os.getenv("DEFAULT_LLM_MODEL", "meta-llama/llama-3-8b-instruct")

def classify_intent_and_extract_keywords(user_message: str, chat_history: list) -> dict:
    """
    Acts as the 'Traffic Cop'. Decides if we need clarifying questions or if we should search the DB.
    Returns a dict: {"action": "clarify" | "search", "reply": "...", "keywords": ["..."]}
    """
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    
    system_prompt = """
    أنت مدير مبيعات ذكي. مهمتك تحليل طلب العميل وتقرير الخطوة التالية:
    1. إذا كان الطلب غير واضح أو عام جداً (مثل: "عندكم عروض؟" أو "أبغى كريم"): 
       يجب أن تطلب توضيحاً بلطف لتحديد المنتج بدقة.
       الرد بصيغة JSON: {"action": "clarify", "reply": "سؤالك الاستيضاحي هنا", "keywords": []}
       
    2. إذا كان الطلب واضحاً ومحدداً (مثل: "بكم عطر ديور؟" أو "أبغى أرز بسمتي"):
       استخرج الكلمات المفتاحية الأساسية للبحث.
       الرد بصيغة JSON: {"action": "search", "reply": "", "keywords": ["عطر", "ديور"]}
       
    يجب أن يكون ردك حصرياً بصيغة JSON قابلة للقراءة البرمجية فقط.
    """
    
    # Constructing simplified prompt list
    messages = [{"role": "system", "content": system_prompt}]
    
    # Add context (history)
    for msg in chat_history[-3:]: # only last 3 to save context
        messages.append({"role": "user", "content": msg})
        
    # Add current message
    messages.append({"role": "user", "content": user_message})
    
    payload = {
        "model": DEFAULT_MODEL,
        "messages": messages,
        "temperature": 0.1, # Low temperature for accurate JSON formatting
        "response_format": {"type": "json_object"}
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        
        # Clean potential markdown markdown ticks
        if content.startswith("```json"):
            content = content.replace("```json", "", 1).strip()
        if content.endswith("```"):
            content = content[:-3].strip()
            
        return json.loads(content)
    except Exception as e:
        print(f"[-] Intent Classification Error: {e}")
        # Default fallback to search with the whole message as keyword
        return {"action": "search", "reply": "", "keywords": [user_message]}

def generate_sales_reply(user_message: str, filtered_products: list) -> str:
    """
    Takes the filtered products and writes a human-like, persuasive Arabic message summarizing them.
    """
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    
    system_prompt = f"""
    أنت بائع سعودي محترف ونشمي. تم جلب هذه المنتجات للعميل من قاعدة بيانات المتجر (Supabase):
    {json.dumps(filtered_products, ensure_ascii=False)}
    
    تعليمات هامة للرد:
    1. اكتب رداً تسويقياً للعميل بناءً على طلبه بلهجة ودودة واحترافية.
    2. استخدم تفاصيل (الوحدة والعبوة) إذا كانت متوفرة ليكون الرد دقيقاً.
    3. إذا كان المنتج (الكمية المتوفرة/stock) صفراً أو غير متوفر، أخبر العميل بلطف أنه غير متوفر حالياً وسنقوم بتوفيره قريباً.
    4. استعرض الأسعار بوضوح.
    5. لا تخترع بيانات أو أسعار من عقلك ابداً.
    """
    
    payload = {
        "model": DEFAULT_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        "temperature": 0.4
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[-] Final Generation Error: {e}")
        return "المعذرة طال عمرك، صار فيه خطأ بسيط بالنظام. ممكن تعيد طلبك؟"
