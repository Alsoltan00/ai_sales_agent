import os
from sqlalchemy import create_engine, text

DB_URL = os.getenv("DATABASE_URL", "")
if DB_URL:
    if DB_URL.startswith("mysql://"):
        DB_URL = DB_URL.replace("mysql://", "mysql+pymysql://", 1)
    elif DB_URL.startswith("postgres://"):
        DB_URL = DB_URL.replace("postgres://", "postgresql+psycopg2://", 1)
    elif DB_URL.startswith("postgresql://") and not DB_URL.startswith("postgresql+psycopg2://"):
        DB_URL = DB_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

engine = create_engine(DB_URL)

with engine.connect() as conn:
    res = conn.execute(text("SELECT * FROM clients WHERE contact_number = '966579331312'"))
    row = res.fetchone()
    if row:
        print(f"FOUND: {row}")
    else:
        print("NOT FOUND")
