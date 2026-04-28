import os
from dotenv import load_dotenv
load_dotenv()
from sqlalchemy import create_engine, text
try:
    url = os.getenv('DATABASE_URL')
    engine = create_engine(url.replace("postgres://", "postgresql+psycopg2://"))
    with engine.connect() as conn:
        res = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'clients'"))
        for row in res:
            print(row)
except Exception as e:
    print(e)
