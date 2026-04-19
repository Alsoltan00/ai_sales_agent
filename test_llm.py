import os
from dotenv import load_dotenv
load_dotenv()

from groq import Groq

# Init Groq
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

def test_manual():
    print("Testing groq...")
    try:
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Output JSON only."},
                {"role": "user", "content": "Hello! Give me a JSON greeting."}
            ],
            model="llama-3.1-8b-instant",
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        print("Works! Output:", response.choices[0].message.content)
    except Exception as e:
        print("Error:", e)
        
test_manual()
