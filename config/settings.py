# config/settings.py
# الإعدادات العامة للنظام

import os
from dotenv import load_dotenv

load_dotenv()

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

# Server
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8000))
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# Sync Intervals
SUPABASE_SYNC_INTERVAL = int(os.getenv("SUPABASE_SYNC_INTERVAL", 5))   # minutes
AIVEN_SYNC_INTERVAL    = int(os.getenv("AIVEN_SYNC_INTERVAL", 5))       # minutes
GSHEETS_SYNC_INTERVAL  = int(os.getenv("GSHEETS_SYNC_INTERVAL", 30))    # minutes
