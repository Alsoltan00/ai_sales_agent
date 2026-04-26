import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.getenv("DATABASE_URL")
if DB_URL and DB_URL.startswith("postgres://"):
    DB_URL = DB_URL.replace("postgres://", "postgresql+psycopg2://")

engine = create_engine(DB_URL)
with engine.connect() as conn:
    print("Admin users:")
    res1 = conn.execute(text("SELECT email, password_hash FROM sales_admin_users;"))
    for row in res1:
        print(dict(row._mapping))
        
    print("Clients:")
    res2 = conn.execute(text("SELECT email, password_hash, contact_number, status FROM clients;"))
    for row in res2:
        print(dict(row._mapping))
