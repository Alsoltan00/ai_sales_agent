import os
from dotenv import load_dotenv
load_dotenv()
from sqlalchemy import create_engine, text
try:
    url = os.getenv('DATABASE_URL')
    if not url:
        print("DATABASE_URL not found")
        exit(1)
    engine = create_engine(url.replace("postgres://", "postgresql+psycopg2://"))
    with engine.connect() as conn:
        res = conn.execute(text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'ai_models_config'"))
        for row in res:
            print(row)
except Exception as e:
    print(e)
