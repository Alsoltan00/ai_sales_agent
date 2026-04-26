import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.getenv("DATABASE_URL")
if DB_URL and DB_URL.startswith("postgres://"):
    DB_URL = DB_URL.replace("postgres://", "postgresql+psycopg2://")

engine = create_engine(DB_URL)

admin_sql = """
INSERT INTO sales_admin_users (name, email, password_hash, permissions)
VALUES ('Super Admin', 'admin@ai-sales.com', 'admin', '{"can_manage_new_clients": true, "can_manage_subscriptions": true, "can_manage_users": true, "is_admin": true}')
ON CONFLICT (email) DO NOTHING;
"""

merchant_sql = """
INSERT INTO clients (company_name, contact_number, email, password_hash, status)
VALUES ('متجر الأمل', '123456789', 'merchant@ai-sales.com', 'merchant', 'active')
ON CONFLICT (email) DO NOTHING;
"""

with engine.begin() as conn:
    conn.execute(text(admin_sql))
    conn.execute(text(merchant_sql))
    print("Users inserted via raw SQL!")
