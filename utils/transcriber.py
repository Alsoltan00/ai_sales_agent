import httpx
import os
import io

async def transcribe_audio(audio_bytes: bytes, api_key: str, filename: str = "voice.ogg") -> str:
    """تحويل الملف الصوتي إلى نص باستخدام Groq أو OpenAI Whisper"""
    if str(api_key).startswith("sk-"):
        url = "https://api.openai.com/v1/audio/transcriptions"
        model = "whisper-1"
    else:
        url = "https://api.groq.com/openai/v1/audio/transcriptions"
        model = "whisper-large-v3"

    headers = {
        "Authorization": f"Bearer {api_key}"
    }
    
    files = {
        "file": (filename, audio_bytes, "audio/ogg"),
        "model": (None, model),
        "language": (None, "ar"),
        "response_format": (None, "json")
    }
    
    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(url, headers=headers, files=files, timeout=30)
            if res.status_code != 200:
                print(f"[WHISPER ERROR] Status: {res.status_code}, Provider: {'OpenAI' if 'openai' in url else 'Groq'}")
                return ""
            
            data = res.json()
            return data.get("text", "")
    except Exception as e:
        print(f"[WHISPER ERROR] Exception: {e}")
        return ""
