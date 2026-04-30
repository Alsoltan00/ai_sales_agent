import edge_tts
import base64
import os
import uuid

async def text_to_speech_b64(text: str, voice: str = "ar-SA-ZariyahNeural") -> str:
    """تحويل النص إلى صوت (Base64) باستخدام edge-tts"""
    try:
        # إنشاء ملف مؤقت
        temp_filename = f"temp_{uuid.uuid4()}.mp3"
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(temp_filename)
        
        # قراءة الملف وتحويله لـ base64
        with open(temp_filename, "rb") as audio_file:
            b64_audio = base64.b64encode(audio_file.read()).decode("utf-8")
        
        # حذف الملف المؤقت
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
            
        return b64_audio
    except Exception as e:
        print(f"[TTS ERROR] {e}")
        return ""
