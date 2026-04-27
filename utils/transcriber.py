import httpx
import os
import io

async def transcribe_audio(audio_bytes: bytes, api_key: str, filename: str = "voice.ogg") -> str:
    """تحويل الملف الصوتي إلى نص باستخدام Groq Whisper"""
    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {
        "Authorization": f"Bearer {api_key}"
    }
    
    files = {
        "file": (filename, audio_bytes, "audio/ogg"),
        "model": (None, "whisper-large-v3"),
        "language": (None, "ar"), # نحدد اللغة العربية لضمان دقة أعلى
        "response_format": (None, "json")
    }
    
    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(url, headers=headers, files=files, timeout=30)
            if res.status_code != 200:
                print(f"[WHISPER ERROR] Status: {res.status_code}, Body: {res.text}")
                return ""
            
            data = res.json()
            return data.get("text", "")
    except Exception as e:
        print(f"[WHISPER ERROR] Exception: {e}")
        return ""
