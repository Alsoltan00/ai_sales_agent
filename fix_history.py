# Script to update chat history injection in ai_engine.py
import pathlib

p = pathlib.Path("merchant/ai_engine.py")
t = p.read_text(encoding="utf-8")
lines = t.splitlines(keepends=True)

new_section = (
    '    # 5. \u062c\u0644\u0628 \u0633\u062c\u0644 \u0627\u0644\u0645\u062d\u0627\u062f\u062b\u0629 \u0627\u0644\u0641\u0639\u0644\u064a (\u0622\u062e\u0631 6 \u0631\u0633\u0627\u0626\u0644) \u0644\u062a\u0645\u0643\u064a\u0646 \u0627\u0644\u0646\u0645\u0648\u0630\u062c \u0645\u0646 \u0641\u0647\u0645 \u0627\u0644\u0633\u064a\u0627\u0642\n'
    '    chat_history_prompt = ""\n'
    '    chat_history_messages = []\n'
    '    try:\n'
    '        history_res = supabase.table("message_logs") \\\n'
    '            .select("message_text, ai_response, timestamp") \\\n'
    '            .order("timestamp", desc=True) \\\n'
    '            .eq("client_id", client_id) \\\n'
    '            .eq("phone_number", phone_number) \\\n'
    '            .limit(6) \\\n'
    '            .execute()\n'
    '        \n'
    '        if history_res.data:\n'
    '            sorted_history = sorted(history_res.data, key=lambda x: x.get("timestamp", ""))\n'
    '            history_lines = []\n'
    '            for msg in sorted_history:\n'
    '                user_msg = (msg.get("message_text") or "").strip()\n'
    '                ai_msg = (msg.get("ai_response") or "").strip()\n'
    '                if user_msg:\n'
    '                    history_lines.append(f"\u0627\u0644\u0639\u0645\u064a\u0644: {user_msg}")\n'
    '                    chat_history_messages.append({"role": "user", "content": user_msg})\n'
    '                if ai_msg:\n'
    '                    history_lines.append(f"\u0623\u0646\u062a: {ai_msg}")\n'
    '                    chat_history_messages.append({"role": "assistant", "content": ai_msg})\n'
    '            if history_lines:\n'
    '                chat_history_prompt = "\\n\u0633\u062c\u0644 \u0627\u0644\u0645\u062d\u0627\u062f\u062b\u0629 \u0627\u0644\u0633\u0627\u0628\u0642\u0629 \u0645\u0639 \u0647\u0630\u0627 \u0627\u0644\u0639\u0645\u064a\u0644 (\u0627\u0642\u0631\u0623\u0647 \u0628\u062f\u0642\u0629 \u0644\u0641\u0647\u0645 \u0627\u0644\u0633\u064a\u0627\u0642):\\n" + "\\n".join(history_lines[-12:]) + "\\n\u062a\u0646\u0628\u064a\u0647: \u0644\u0627 \u062a\u0643\u0631\u0631 \u0627\u0644\u062a\u062d\u064a\u0629. \u0623\u0643\u0645\u0644 \u0627\u0644\u0645\u062d\u0627\u062f\u062b\u0629 \u0628\u0634\u0643\u0644 \u0637\u0628\u064a\u0639\u064a.\\n"\n'
    '    except Exception as e:\n'
    '        print(f"Warning: Could not fetch chat history: {e}")\n'
    '\n'
)

new_lines = lines[:190] + [new_section] + lines[206:]
p.write_text("".join(new_lines), encoding="utf-8")
print("DONE - chat history injection updated successfully")
