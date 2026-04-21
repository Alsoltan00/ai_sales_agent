import os
from dotenv import load_dotenv
load_dotenv()

from groq import Groq
import json

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

DEFAULT_MODEL = "llama-3.3-70b-versatile"

def classify(user_message):
    system_prompt = """
    أنت موظف مبيعات ذكي ومحترف، تتحدث باللهجة السعودية.
    مهمتك تحليل رسالة العميل وإخراج رد بصيغة JSON فقط، يحتوي على مفتاحين:
    1. "action": اختر "chat" إذا كانت الرسالة ترحيبية أو عامة (مثل: كيف الحال، سلام، من أنتم).
                 اختر "search" إذا كان العميل يسأل عن توفر منتج أو سعره (مثل: بكم العطر؟، عندكم رز؟).
                 اختر "clarify" إذا كان الطلب ناقصاً جداً ويحتاج توضيح (مثل: أبغى شيء رخيص).
    2. "reply": إذا كان الخيار chat أو clarify، اكتب ردك الودود هنا. أما إذا كان search اتركه فارغاً "".
    3. "keywords": إذا كان الخيار search، ضع هنا الكلمات المفتاحية للبحث كقائمة (مثل: ["عطر", "ديور"]). وإلا اتركها فارغة [].

    المخرجات يجب أن تكون JSON فقط.
    """
    
    try:
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        print(f"Message: {user_message}")
        print(response.choices[0].message.content)
        print("-" * 20)
    except Exception as e:
        print("Error:", e)
        
classify("سلام عليكم وش اخباركم")
classify("بكم عطر كريد افينتوس")
classify("لو سمحت ابغى كريم")
