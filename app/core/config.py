import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    PROJECT_NAME: str = "AI Sales SaaS Platform"
    PROJECT_VERSION: str = "2.0.0"
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL")
    
    # Security
    SECRET_KEY: str = os.getenv("SESSION_SECRET", "super-secret-key-123")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 1 week
    
    # WhatsApp API (Evolution)
    EVOLUTION_API_URL: str = os.getenv("EVOLUTION_API_URL", "").rstrip('/')
    EVOLUTION_API_KEY: str = os.getenv("EVOLUTION_API_KEY", "")
    
    # AI (Groq/OpenRouter)
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY")

settings = Settings()
