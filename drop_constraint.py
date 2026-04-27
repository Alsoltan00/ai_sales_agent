import os
from dotenv import load_dotenv
load_dotenv()
from sqlalchemy import create_engine, text
engine = create_engine(os.getenv('DATABASE_URL').replace("postgres://", "postgresql+psycopg2://"))
with engine.connect() as conn:
    print([r for r in conn.execute(text("SELECT constraint_name FROM information_schema.table_constraints WHERE table_name = 'ai_models_config' AND constraint_type = 'UNIQUE'"))])
    try:
        conn.execute(text("ALTER TABLE ai_models_config DROP CONSTRAINT ai_models_config_client_id_key"))
        conn.commit()
        print("Dropped UNIQUE constraint successfully.")
    except Exception as e:
        print("Error or constraint doesn't exist:", e)
