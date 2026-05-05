# Script to inject chat_history_messages into the messages array
import pathlib

p = pathlib.Path("merchant/ai_engine.py")
t = p.read_text(encoding="utf-8")

# Fix 1: Add chat_history_messages to image/audio path
old1 = '''        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content_parts}
        ]'''

new1 = '''        messages = [
            {"role": "system", "content": system_prompt},
        ]
        # Inject conversation history for context
        if chat_history_messages:
            messages.extend(chat_history_messages[-8:])
        messages.append({"role": "user", "content": content_parts})'''

t = t.replace(old1, new1)

# Fix 2: Add chat_history_messages to text path
old2 = '''        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": final_msg}
        ]'''

new2 = '''        messages = [
            {"role": "system", "content": system_prompt},
        ]
        # Inject conversation history for context
        if chat_history_messages:
            messages.extend(chat_history_messages[-8:])
        messages.append({"role": "user", "content": final_msg})'''

t = t.replace(old2, new2)

p.write_text(t, encoding="utf-8")
print("DONE - chat history messages injected into API calls")
