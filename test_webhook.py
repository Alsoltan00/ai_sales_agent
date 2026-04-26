import httpx
import asyncio

# --- استبدل هذه القيم بما يطابق إعدادات التاجر في قاعدة البيانات المحلية لديك ---
# للواتساب (Evolution API)
EVOLUTION_INSTANCE_NAME = "instance1" 
WHATSAPP_PHONE_NUMBER = "966500000000"

# لتيليجرام
TELEGRAM_BOT_TOKEN = "your_bot_token_here"
TELEGRAM_CHAT_ID = 123456789

async def test_whatsapp_evolution():
    print("🚀 جاري اختبار ويب هوك واتساب (Evolution API)...")
    url = f"http://localhost:8000/webhook/whatsapp/evolution/{EVOLUTION_INSTANCE_NAME}"
    
    payload = {
        "event": "messages.upsert",
        "data": {
            "key": {
                "remoteJid": WHATSAPP_PHONE_NUMBER,
                "fromMe": False,
                "id": "1234567890"
            },
            "message": {
                "conversation": "مرحباً، هل لديكم عروض جديدة؟"
            }
        }
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload)
            print(f"✅ نتيجة واتساب: {response.status_code}")
        except Exception as e:
            print(f"❌ خطأ في واتساب: {e}")

async def test_telegram():
    print("\n🚀 جاري اختبار ويب هوك تيليجرام...")
    url = f"http://localhost:8000/webhook/telegram/{TELEGRAM_BOT_TOKEN}"
    
    payload = {
        "update_id": 10000,
        "message": {
            "message_id": 1365,
            "from": {
                "id": TELEGRAM_CHAT_ID,
                "first_name": "Test",
                "username": "testuser"
            },
            "chat": {
                "id": TELEGRAM_CHAT_ID,
                "first_name": "Test",
                "username": "testuser",
                "type": "private"
            },
            "date": 1441645532,
            "text": "مرحباً، كم سعر المنتج الأول؟"
        }
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload)
            print(f"✅ نتيجة تيليجرام: {response.status_code}")
        except Exception as e:
            print(f"❌ خطأ في تيليجرام: {e}")

async def main():
    print("--- 🧪 اختبار استقبال الرسائل للوكيل الذكي ---")
    await test_whatsapp_evolution()
    await test_telegram()
    print("-----------------------------------------------")
    print("ملاحظة: لكي يعمل الاختبار بشكل كامل ويصلك رد، يجب أن يكون:")
    print("1. التاجر مضاف في قاعدة البيانات وتمت تهيئة إعدادات الوكيل والذكاء الاصطناعي الخاصة به.")
    print("2. أرقام الهاتف المستخدمة في هذا الاختبار مضافة في قائمة 'الأرقام المصرحة' للتاجر (أو ميزة السماح للجميع مفعلة).")
    print("3. إعدادات الـ API لقنوات الإرسال (Evolution / Telegram) صحيحة ليتمكن السيرفر من إرسال الرد الفعلي.")

if __name__ == "__main__":
    asyncio.run(main())
