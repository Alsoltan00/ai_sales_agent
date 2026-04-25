import os
from groq import Groq
from edge_tts import Communicate

def get_groq_client():
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if api_key:
        try:
            return Groq(api_key=api_key)
        except Exception:
            pass
    return None

def recognize_speech(audio_file_path: str) -> str:
    """
    Uses Groq's Whisper-large-v3 API to transcribe WhatsApp voice notes instantly.
    """
    client = get_groq_client()
    try:
        if not client:
            return "Error: No GROQ_API_KEY found or valid."

        with open(audio_file_path, "rb") as file:
            transcription = client.audio.transcriptions.create(
                file=(audio_file_path, file.read()),
                model="whisper-large-v3",
                response_format="text",
                language="ar", # Force Arabic for better results
                temperature=0.0
            )
            return transcription
    except Exception as e:
        print(f"[!] STT Error: {e}")
        return ""

async def text_to_speech(text: str, output_path: str):
    """
    Converts the final Arabic text pitch into a high-quality audio file using Edge-TTS.
    Uses 'ar-SA-HamedNeural' which is one of the best Saudi voices available.
    """
    try:
        # Saudi voice: ar-SA-HamedNeural or ar-SA-ZariNeural
        voice = "ar-SA-HamedNeural"
        communicate = Communicate(text, voice)
        await communicate.save(output_path)
        print(f"[+] TTS Audio saved to: {output_path}")
    except Exception as e:
        print(f"[!] TTS Error: {e}")
