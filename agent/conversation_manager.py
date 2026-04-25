import os
import requests

# Set placeholders for now, the user needs to configure these in a .env file later
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "https://evolution-api-latest-qxsg.onrender.com")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "Aseel.709293")

from agent.llm_router import classify_intent_and_extract_keywords, generate_sales_reply
from agent.database import search_products, get_store_config, check_authorized_number
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
    Supports Multi-Tenancy based on the instance name.
    """
    try:
        # 1. Detect Instance and Fetch Store Config
        instance_name = payload.get("instance", "asil-phone")
        store_config = get_store_config(instance_name)
        
        if not store_config:
            print(f"[-] No store configuration found for instance: {instance_name}")
            return
            
        store_id = store_config.get("id")
        store_name = store_config.get("name")
        custom_prompt = store_config.get("system_prompt")

        # 2. Parse Key Information from Payload
        data = payload.get("data", {})
        key = data.get("key", {})
        message = data.get("message", {})
        
        # [NEW] Loop Prevention: Ignore messages from the bot itself
        if key.get("fromMe") is True:
            return

        remote_jid = key.get("remoteJid")
        if not remote_jid:
            print("[-] No remoteJid found in payload.")
            return
            
        print(f"[*] Received message from: {remote_jid}")

        # 1. Block Group Chats Completely
        if remote_jid.endswith("@g.us"):
            print(f"[-] Ignored group message from {remote_jid}")
            return

        # 3. Strict Whitelist Filtering (Supabase-driven)
        clean_number = "".join(filter(str.isdigit, remote_jid.split("@")[0]))
        
        print(f"[*] Checking whitelist for: {clean_number} in store {store_name}")
        is_auth = check_authorized_number(clean_number, store_id)
        print(f"[*] Whitelist check result: {is_auth}")

        if not is_auth:
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
        intent_data = classify_intent_and_extract_keywords(text, history, store_name, custom_prompt)
        
        if intent_data.get("action") in ["clarify", "chat"]:
            final_response_text = intent_data.get("reply", "أهلاً بك! كيف يمكنني مساعدتك اليوم؟")
        else:
            keywords = intent_data.get("keywords", [])
            filtered_products = search_products(keywords, store_id)
            
            # Pass history for contextual product advice
            final_response_text = generate_sales_reply(text, filtered_products, history, store_name, custom_prompt)

        # [NEW] Rich Memory: Remember full role-based context
        conversation_history[remote_jid].append({"role": "user", "content": text})
        conversation_history[remote_jid].append({"role": "assistant", "content": final_response_text})

        # Keep history concise (last 10 interactions)
        if len(conversation_history[remote_jid]) > 10:
            conversation_history[remote_jid] = conversation_history[remote_jid][-10:]

        # 4. Send the Text Reply back to WhatsApp IMMEDIATELY for speed
        send_whatsapp_text(remote_jid, final_response_text, instance_name)

        # 5. Create and Send the Voice Response in the background
        voice_path = f"temp_reply_{uuid.uuid4().hex}.mp3"
        try:
            await text_to_speech(final_response_text, voice_path)
            send_whatsapp_audio(remote_jid, voice_path, instance_name)
        except Exception as ve:
            print(f"[!] Voice generation error: {ve}")
        
        # Cleanup temp file
        if os.path.exists(voice_path):
            os.remove(voice_path)

    except Exception as e:
        print(f"[!] Critical Error in Conversation Manager: {e}")

def send_whatsapp_text(remote_jid: str, text: str, instance_name: str):
    """
    Sends a text message using Evolution API.
    """
    url = f"{EVOLUTION_API_URL}/message/sendText/{instance_name}"
    
    headers = {
        "apikey": EVOLUTION_API_KEY,
        "Content-Type": "application/json"
    }
    
    # Sanitize remote_jid to get only the numeric part for Evolution API
    clean_number = remote_jid.split("@")[0]
    
    body = {
        "number": clean_number,
        "text": text
    }
    
    print(f"[*] Attempting to send text to {clean_number} via {instance_name}...")
    response = requests.post(url, headers=headers, json=body)
    
    if response.status_code in [200, 201]:
        print(f"[+] Successfully sent message to {clean_number}")
    else:
        print(f"[!] Failed to send message (HTTP {response.status_code}): {response.text}")

def send_whatsapp_audio(remote_jid: str, audio_path: str, instance_name: str):
    """
    Sends an audio file as a PTT (Voice Note) via Evolution API using Base64.
    """
    url = f"{EVOLUTION_API_URL}/message/sendWhatsAppAudio/{instance_name}"
    
    # Sanitize number
    clean_number = remote_jid.split("@")[0]
    
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
