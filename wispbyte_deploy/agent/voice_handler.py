import os
from groq import Groq
from edge_tts import Communicate

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY)

def recognize_speech(audio_file_path: str) -> str:
    """
    Uses Groq's Whisper-large-v3 API to transcribe WhatsApp voice notes instantly.
    """
    try:
        if not GROQ_API_KEY:
            return "Error: No GROQ_API_KEY found."

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
