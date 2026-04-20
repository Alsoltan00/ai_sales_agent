import os
import requests

# Set placeholders for now, the user needs to configure these in a .env file later
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "https://evolution-api-latest-qxsg.onrender.com")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "Aseel.709293")

from agent.llm_router import classify_intent_and_extract_keywords, generate_sales_reply
from agent.supabase_db import search_products
from agent.voice_handler import recognize_speech, text_to_speech
import base64
import uuid
import shutil

# In-memory dictionary to store simple conversation histories
# Key: remote_jid, Value: list of message strings
conversation_history = {}

async def handle_incoming_message(payload: dict):
    """
    Parses the webhook payload from Evolution API and orchestrates the response.
    """
    try:
        # 1. Parse Key Information from Payload
        data = payload.get("data", {})
        key = data.get("key", {})
        message = data.get("message", {})
        
        remote_jid = key.get("remoteJid")
        if not remote_jid:
            return
            
        print(f"[*] Received message from: {remote_jid}")

        # 1. Block Group Chats Completely
        if remote_jid.endswith("@g.us"):
            print(f"[-] Ignored group message from {remote_jid}")
            return

        # 2. Strict Whitelist Filtering
        # Read from environment, or use the default array of allowed numbers.
        allowed_env = os.getenv("ALLOWED_NUMBERS", "966579331312,966501683230,966549852342,966501018908,967776803879")
        allowed_numbers = [num.strip() for num in allowed_env.split(",") if num.strip()]
        
        clean_number = remote_jid.split("@")[0]
        
        # If allowed_numbers list is NOT empty, verify the sender.
        if allowed_numbers and clean_number not in allowed_numbers:
            print(f"[-] Ignored message from unauthorized number: {clean_number}")
            return

        # 2. Extract Text or Audio
        text = ""
        is_audio = False
        audio_url = ""
        
        # Check for Text
        if "conversation" in message:
            text = message["conversation"]
        elif "extendedTextMessage" in message:
            text = message["extendedTextMessage"].get("text", "")
        
        # Check for Audio (Voice Note)
        elif "audioMessage" in message:
            is_audio = True
            audio_url = message["audioMessage"].get("url")
            print(f"[*] Received voice note: {audio_url}")

        if not text and not is_audio:
            print("[-] No valid text or audio found in message")
            return

        # 2.1 Handle Audio Transcription if needed
        if is_audio and audio_url:
            text = await process_incoming_audio(audio_url)
            if not text:
                print("[-] Could not transcribe audio.")
                return

        print(f"[*] Processed message: {text}")
        
        # Initialize history if missing
        if remote_jid not in conversation_history:
            conversation_history[remote_jid] = []
            
        history = conversation_history[remote_jid]

        # 3. Process Intent (The Intelligent Dispatcher)
        intent_data = classify_intent_and_extract_keywords(text, history)
        
        if intent_data.get("action") in ["clarify", "chat"]:
            # The sales agent generates a direct response (greeting, chat, or clarification)
            final_response_text = intent_data.get("reply", "أهلاً بك! كيف يمكنني مساعدتك اليوم؟")
            print(f"[i] Action: Direct Reply ({intent_data.get('action')})")
        else:
            # Action is 'search'
            keywords = intent_data.get("keywords", [])
            print(f"[i] Action: Searching DB for: {keywords}")
            
            # Fetch and filter from Supabase
            filtered_products = search_products(keywords)
            
            # Generate personalized pitch based on actual available inventory
            final_response_text = generate_sales_reply(text, filtered_products)
            print("[i] Generated Sales Pitch")

        # Remember latest message to keep context
        conversation_history[remote_jid].append(text)

        # 4. Create the Voice Response
        voice_path = f"temp_reply_{uuid.uuid4().hex}.mp3"
        await text_to_speech(final_response_text, voice_path)

        # 5. Send the Replies back to WhatsApp (Both Text and Audio for premium feel)
        send_whatsapp_text(remote_jid, final_response_text)
        send_whatsapp_audio(remote_jid, voice_path)
        
        # Cleanup temp file
        if os.path.exists(voice_path):
            os.remove(voice_path)

    except Exception as e:
        print(f"[!] Critical Error in Conversation Manager: {e}")

def send_whatsapp_text(remote_jid: str, text: str):
    """
    Sends a text message using Evolution API exactly like the N8N HTTP Request node did.
    """
    # The Evolution API sender url format depending on your setup.
    # Usually it's /message/sendText/{instanceName}
    # Currently hardcoded to "asil-phone" based on the previous json configuration.
    instance_name = os.getenv("EVOLUTION_INSTANCE_NAME", "asil-phone")
    url = f"{EVOLUTION_API_URL}/message/sendText/{instance_name}"
    
    headers = {
        "apikey": EVOLUTION_API_KEY,
        "Content-Type": "application/json"
    }
    
    body = {
        "number": remote_jid,
        "text": text
    }
    
    response = requests.post(url, headers=headers, json=body)
    
    if response.status_code == 200 or response.status_code == 201:
        print(f"[+] Successfully sent message to {remote_jid}")
    else:
        print(f"[-] Failed to send message: {response.text}")

def send_whatsapp_audio(remote_jid: str, audio_path: str):
    """
    Sends an audio file as a PTT (Voice Note) via Evolution API using Base64.
    """
    instance_name = os.getenv("EVOLUTION_INSTANCE_NAME", "asil-phone")
    url = f"{EVOLUTION_API_URL}/message/sendWhatsAppAudio/{instance_name}"
    
    try:
        with open(audio_path, "rb") as f:
            audio_base64 = base64.b64encode(f.read()).decode("utf-8")
        
        headers = {
            "apikey": EVOLUTION_API_KEY,
            "Content-Type": "application/json"
        }
        
        body = {
            "number": remote_jid,
            "audio": f"data:audio/mp3;base64,{audio_base64}",
            "encoding": True
        }
        
        response = requests.post(url, headers=headers, json=body)
        if response.status_code in [200, 201]:
            print(f"[+] Successfully sent voice note to {remote_jid}")
        else:
            print(f"[-] Failed to send voice note: {response.text}")
    except Exception as e:
        print(f"[!] Error sending audio: {e}")

async def process_incoming_audio(url: str) -> str:
    """
    Downloads audio from Evolution API and transcribes it.
    """
    temp_file = f"incoming_{uuid.uuid4().hex}.ogg"
    try:
        # Download the file
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            with open(temp_file, "wb") as f:
                shutil.copyfileobj(response.raw, f)
            
            # Transcribe
            text = recognize_speech(temp_file)
            return text
    except Exception as e:
        print(f"[!] Transcription processor error: {e}")
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)
    return ""
