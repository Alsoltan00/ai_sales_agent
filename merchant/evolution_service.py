"""
merchant/evolution_service.py
خدمة إدارة جلسات Evolution API تلقائياً
- إنشاء جلسة لكل تاجر
- جلب QR Code للمسح
- التحقق من حالة الاتصال
- إعداد Webhook تلقائياً
"""
import os
import httpx
from database.db_client import get_db_client

# إعدادات خادم Evolution API (يضبطها المسؤول)
EVOLUTION_SERVER_URL = os.getenv("EVOLUTION_API_URL", "").rstrip("/")
EVOLUTION_GLOBAL_KEY = os.getenv("EVOLUTION_API_KEY", "")


def _headers():
    """ترويسات الطلبات لخادم Evolution"""
    return {
        "apikey": EVOLUTION_GLOBAL_KEY,
        "Content-Type": "application/json"
    }


def _instance_name(client_id: str) -> str:
    """توليد اسم جلسة فريد لكل تاجر"""
    short_id = str(client_id).replace("-", "")[:12]
    return f"merchant_{short_id}"


async def create_instance(client_id: str, webhook_base_url: str) -> dict:
    """
    إنشاء جلسة Evolution API جديدة للتاجر وإعداد الـ Webhook تلقائياً.
    يعيد: {"success": True/False, "instance_name": "...", "qrcode": "base64..."}
    """
    instance = _instance_name(client_id)
    webhook_url = f"{webhook_base_url}/webhook/whatsapp/evolution/{instance}"

    # 1. إنشاء الجلسة
    create_payload = {
        "instanceName": instance,
        "qrcode": True,
        "integration": "WHATSAPP-BAILEYS",
        "webhook": {
            "url": webhook_url,
            "byEvents": False,
            "base64": True,
            "events": [
                "MESSAGES_UPSERT"
            ]
        }
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # محاولة إنشاء الجلسة
            res = await client.post(
                f"{EVOLUTION_SERVER_URL}/instance/create",
                json=create_payload,
                headers=_headers()
            )

            data = res.json()

            if res.status_code in (200, 201):
                # حفظ بيانات الجلسة في قاعدة البيانات
                _save_instance_config(client_id, instance)

                qr_base64 = None
                # استخراج QR code من الرد
                if isinstance(data, dict):
                    qr_data = data.get("qrcode", {})
                    if isinstance(qr_data, dict):
                        qr_base64 = qr_data.get("base64")
                    elif isinstance(qr_data, str):
                        qr_base64 = qr_data

                return {
                    "success": True,
                    "instance_name": instance,
                    "qrcode": qr_base64,
                    "message": "تم إنشاء الجلسة بنجاح"
                }
            else:
                # ربما الجلسة موجودة مسبقاً
                error_msg = data.get("message", str(data)) if isinstance(data, dict) else str(data)
                if "already" in str(error_msg).lower() or "instance" in str(error_msg).lower():
                    # الجلسة موجودة، نحاول جلب QR Code مباشرة
                    return await get_qr_code(client_id)
                return {"success": False, "message": f"خطأ: {error_msg}"}

    except Exception as e:
        print(f"[EVOLUTION] Create instance error: {e}")
        return {"success": False, "message": f"فشل الاتصال بخادم Evolution: {e}"}


async def get_qr_code(client_id: str) -> dict:
    """
    جلب QR Code لجلسة التاجر الحالية.
    """
    instance = _instance_name(client_id)

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            res = await client.get(
                f"{EVOLUTION_SERVER_URL}/instance/connect/{instance}",
                headers=_headers()
            )

            if res.status_code == 200:
                data = res.json()
                qr_base64 = None

                if isinstance(data, dict):
                    qr_base64 = data.get("base64") or data.get("qrcode", {}).get("base64")
                    # أحياناً يكون داخل code
                    if not qr_base64:
                        code = data.get("code")
                        if code and isinstance(code, str) and len(code) > 100:
                            qr_base64 = code

                return {
                    "success": True,
                    "instance_name": instance,
                    "qrcode": qr_base64,
                    "message": "تم جلب QR Code بنجاح"
                }
            else:
                return {"success": False, "message": "فشل جلب QR Code"}

    except Exception as e:
        print(f"[EVOLUTION] QR code error: {e}")
        return {"success": False, "message": f"خطأ في الاتصال: {e}"}


async def check_connection_status(client_id: str) -> dict:
    """
    التحقق من حالة اتصال واتساب للتاجر.
    يعيد: {"connected": True/False, "phone": "966...", "name": "..."}
    """
    instance = _instance_name(client_id)

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.get(
                f"{EVOLUTION_SERVER_URL}/instance/connectionState/{instance}",
                headers=_headers()
            )

            if res.status_code == 200:
                data = res.json()
                state = ""
                if isinstance(data, dict):
                    state = data.get("state") or data.get("instance", {}).get("state", "")

                is_connected = state.lower() in ("open", "connected")

                result = {
                    "success": True,
                    "connected": is_connected,
                    "state": state,
                    "instance_name": instance
                }

                # محاولة جلب معلومات الرقم إذا كان متصلاً
                if is_connected:
                    try:
                        info_res = await client.get(
                            f"{EVOLUTION_SERVER_URL}/instance/fetchInstances",
                            headers=_headers(),
                            params={"instanceName": instance}
                        )
                        if info_res.status_code == 200:
                            info_data = info_res.json()
                            if isinstance(info_data, list) and info_data:
                                inst_info = info_data[0].get("instance", {})
                                result["phone"] = inst_info.get("owner", "").split("@")[0] if inst_info.get("owner") else ""
                                result["name"] = inst_info.get("profileName", "")
                    except:
                        pass

                return result
            else:
                return {"success": True, "connected": False, "state": "close"}

    except Exception as e:
        print(f"[EVOLUTION] Connection check error: {e}")
        return {"success": False, "connected": False, "state": "error", "message": str(e)}


async def disconnect_instance(client_id: str) -> dict:
    """
    قطع اتصال واتساب وحذف الجلسة.
    """
    instance = _instance_name(client_id)

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # تسجيل خروج أولاً
            await client.delete(
                f"{EVOLUTION_SERVER_URL}/instance/logout/{instance}",
                headers=_headers()
            )
            # ثم حذف الجلسة
            await client.delete(
                f"{EVOLUTION_SERVER_URL}/instance/delete/{instance}",
                headers=_headers()
            )

        # مسح البيانات من قاعدة البيانات
        _clear_instance_config(client_id)

        return {"success": True, "message": "تم قطع الاتصال بنجاح"}

    except Exception as e:
        print(f"[EVOLUTION] Disconnect error: {e}")
        return {"success": False, "message": f"خطأ: {e}"}


async def set_webhook(client_id: str, webhook_base_url: str) -> dict:
    """
    تسجيل Webhook تلقائياً بعد الاتصال.
    """
    instance = _instance_name(client_id)
    webhook_url = f"{webhook_base_url}/webhook/whatsapp/evolution/{instance}"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.post(
                f"{EVOLUTION_SERVER_URL}/webhook/set/{instance}",
                json={
                    "url": webhook_url,
                    "webhook_by_events": False,
                    "webhook_base64": True,
                    "events": ["MESSAGES_UPSERT"]
                },
                headers=_headers()
            )
            return {"success": res.status_code in (200, 201)}
    except Exception as e:
        print(f"[EVOLUTION] Webhook set error: {e}")
        return {"success": False}


def _save_instance_config(client_id: str, instance_name: str):
    """حفظ بيانات الجلسة في channels_config"""
    db = get_db_client()
    try:
        existing = db.table("channels_config").select("id").eq("client_id", client_id).execute()

        update_data = {
            "client_id": client_id,
            "whatsapp_provider": "evolution",
            "evolution_api_url": EVOLUTION_SERVER_URL,
            "evolution_api_key": EVOLUTION_GLOBAL_KEY,
            "evolution_instance_name": instance_name
        }

        if existing.data:
            db.table("channels_config").update(update_data).eq("client_id", client_id).execute()
        else:
            db.table("channels_config").insert(update_data).execute()
    except Exception as e:
        print(f"[EVOLUTION] Save config error: {e}")


def _clear_instance_config(client_id: str):
    """مسح بيانات الجلسة"""
    db = get_db_client()
    try:
        db.table("channels_config").update({
            "evolution_instance_name": None,
        }).eq("client_id", client_id).execute()
    except Exception as e:
        print(f"[EVOLUTION] Clear config error: {e}")
