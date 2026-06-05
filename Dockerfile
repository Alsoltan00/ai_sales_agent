# ─── Hugging Face Spaces — Docker SDK ─────────────────────────────────────────
# يستخدم بورت 7860 (الافتراضي لـ HF Spaces)

FROM python:3.12-slim

# تثبيت المكتبات النظامية المطلوبة لـ psycopg2 و pydub (ffmpeg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# مجلد العمل
WORKDIR /app

# نسخ ملف المتطلبات أولاً للاستفادة من التخزين المؤقت
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ كل ملفات المشروع
COPY . .

# Hugging Face Spaces يستخدم بورت 7860 افتراضياً
EXPOSE 7860

# تشغيل الخادم
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
