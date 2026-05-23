"""
merchant/reception/buttons_handler.py
نظام الأزرار التفاعلية الذكية
يقوم بتحليل رد الذكاء الاصطناعي واكتشاف الخيارات المتعددة وتحويلها إلى أزرار تفاعلية
"""
import re
import httpx
import json


def extract_buttons_from_reply(ai_reply: str) -> tuple:
    """
    يحلل رد الذكاء الاصطناعي ويكتشف الخيارات المعروضة كأزرار محتملة.
    
    يدعم أنماط متعددة:
    1. [BUTTONS: btn1 | btn2 | btn3] — وسم صريح من الذكاء الاصطناعي
    2. اكتشاف تلقائي للخيارات المرقمة مثل: 1. خيار أ  2. خيار ب
    
    Returns:
        tuple: (clean_text, buttons_list)
        - clean_text: النص بدون وسم الأزرار
        - buttons_list: قائمة الأزرار [{"id": "1", "text": "..."}, ...]
    """
    buttons = []
    clean_text = ai_reply
    
    # النمط 1: وسم صريح [BUTTONS: btn1 | btn2 | btn3]
    tag_pattern = r'\[BUTTONS:\s*(.+?)\]'
    tag_match = re.search(tag_pattern, ai_reply)
    if tag_match:
        raw_buttons = tag_match.group(1)
        btn_texts = [b.strip() for b in raw_buttons.split("|") if b.strip()]
        for i, txt in enumerate(btn_texts[:3]):  # واتساب يدعم 3 أزرار كحد أقصى
            buttons.append({"id": f"btn_{i+1}", "text": txt[:20]})  # الحد 20 حرف
        clean_text = re.sub(tag_pattern, '', ai_reply).strip()
        return clean_text, buttons
    
    # النمط 2: اكتشاف تلقائي للخيارات المرقمة
    # يبحث عن أنماط مثل: 1. خيار أ\n2. خيار ب\n3. خيار ج
    # أو: 1- خيار أ\n2- خيار ب
    # أو: ١. خيار أ\n٢. خيار ب
    numbered_pattern = r'(?:^|\n)\s*[١٢٣1-3][\.\-\)]\s*(.+?)(?=\n|$)'
    numbered_matches = re.findall(numbered_pattern, ai_reply)
    
    if 2 <= len(numbered_matches) <= 3:
        for i, match in enumerate(numbered_matches):
            btn_text = match.strip()
            # تنظيف النص: إزالة الرموز والنجوم
            btn_text = re.sub(r'[\*\*]', '', btn_text).strip()
            # اختصار إذا كان طويلاً
            if len(btn_text) > 20:
                btn_text = btn_text[:18] + ".."
            buttons.append({"id": f"opt_{i+1}", "text": btn_text})
    
    # النمط 3: أسئلة نعم/لا
    yes_no_patterns = [
        r'هل\s+(?:ترغب|تريد|تود|توافق|تحب)',
        r'هل\s+هذ[اه]\s+صحيح',
        r'هل\s+البيانات\s+صحيحة',
    ]
    for pattern in yes_no_patterns:
        if re.search(pattern, ai_reply):
            buttons = [
                {"id": "yes", "text": "نعم ✅"},
                {"id": "no", "text": "لا ❌"}
            ]
            break
    
    return clean_text, buttons


async def send_evolution_buttons(api_url: str, api_key: str, instance_name: str,
                                  phone: str, text: str, buttons: list) -> bool:
    """إرسال رسالة مع أزرار تفاعلية عبر Evolution API"""
    clean_number = phone.split("@")[0]
    url = f"{api_url.rstrip('/')}/message/sendButtons/{instance_name}"
    headers = {"apikey": api_key, "Content-Type": "application/json"}
    
    # تجهيز الأزرار بتنسيق Evolution API
    evo_buttons = []
    for btn in buttons[:3]:
        evo_buttons.append({
            "type": "reply",
            "reply": {
                "id": btn["id"],
                "title": btn["text"]
            }
        })
    
    payload = {
        "number": clean_number,
        "title": "",
        "description": text,
        "footer": "",
        "buttons": evo_buttons
    }
    
    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(url, json=payload, headers=headers, timeout=15)
            if res.status_code < 400:
                print(f"[BUTTONS] Evolution buttons sent successfully to {clean_number}")
                return True
            else:
                print(f"[BUTTONS] Evolution buttons failed ({res.status_code}): {res.text}")
                return False
    except Exception as e:
        print(f"[BUTTONS ERROR] Evolution: {e}")
        return False


async def send_official_buttons(access_token: str, phone_number_id: str,
                                 to_phone: str, text: str, buttons: list) -> bool:
    """إرسال رسالة مع أزرار تفاعلية عبر WhatsApp Cloud API الرسمي"""
    url = f"https://graph.facebook.com/v19.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    # تجهيز الأزرار بتنسيق Meta Cloud API
    meta_buttons = []
    for btn in buttons[:3]:
        meta_buttons.append({
            "type": "reply",
            "reply": {
                "id": btn["id"],
                "title": btn["text"]
            }
        })
    
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_phone,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": text},
            "action": {
                "buttons": meta_buttons
            }
        }
    }
    
    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(url, headers=headers, json=payload, timeout=15)
            if res.status_code < 400:
                print(f"[BUTTONS] Official buttons sent successfully to {to_phone}")
                return True
            else:
                print(f"[BUTTONS] Official buttons failed ({res.status_code}): {res.text}")
                return False
    except Exception as e:
        print(f"[BUTTONS ERROR] Official: {e}")
        return False


async def send_telegram_buttons(bot_token: str, chat_id: int, text: str, buttons: list) -> bool:
    """إرسال رسالة مع أزرار تفاعلية عبر تيليجرام"""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    # تجهيز الأزرار بتنسيق Telegram Inline Keyboard
    keyboard_rows = []
    for btn in buttons:
        keyboard_rows.append([{
            "text": btn["text"],
            "callback_data": btn["id"]
        }])
    
    payload = {
        "chat_id": chat_id,
        "text": text,
        "reply_markup": json.dumps({
            "inline_keyboard": keyboard_rows
        })
    }
    
    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(url, json=payload, timeout=10)
            if res.status_code < 400:
                print(f"[BUTTONS] Telegram buttons sent successfully to {chat_id}")
                return True
            else:
                print(f"[BUTTONS] Telegram buttons failed ({res.status_code}): {res.text}")
                return False
    except Exception as e:
        print(f"[BUTTONS ERROR] Telegram: {e}")
        return False
