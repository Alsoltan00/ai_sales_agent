# merchant/ai_training/model_selector.py
# واجهة اختيار نموذج الذكاء الاصطناعي
# النماذج المدعومة: GPT-4, Claude, Gemini, Groq, ...
# عند تحديد نموذج تظهر الخانات المطلوبة (API Key, Model ID, ...)

SUPPORTED_MODELS = [
    {"name": "GPT-4o",       "provider": "openai",     "fields": ["api_key", "model_id"]},
    {"name": "Claude 3",     "provider": "anthropic",  "fields": ["api_key", "model_id"]},
    {"name": "Gemini Pro",   "provider": "google",     "fields": ["api_key", "model_id"]},
    {"name": "Groq LLaMA",   "provider": "groq",       "fields": ["api_key", "model_id"]},
    {"name": "OpenRouter",   "provider": "openrouter", "fields": ["api_key", "model_id"]},
]

def get_supported_models() -> list:
    return SUPPORTED_MODELS

def get_model_fields(model_name: str) -> list:
    pass
