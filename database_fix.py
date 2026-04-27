from sqlalchemy import create_engine, text

# بيانات الاتصال
DATABASE_URL = "postgresql://asil00:S6eYjD7iO3-A-hL67gRFrQ@fastapi-ai-db-asil00.a.aivencloud.com:11746/defaultdb?sslmode=require"

def fix_database():
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        print("Checking for column 'ignore_groups'...")
        try:
            # إضافة العمود إذا لم يكن موجوداً
            conn.execute(text("ALTER TABLE clients ADD COLUMN IF NOT EXISTS ignore_groups BOOLEAN DEFAULT TRUE;"))
            conn.commit()
            print("[SUCCESS] Column 'ignore_groups' added or already exists.")
        except Exception as e:
            print(f"[ERROR] Failed to add column: {e}")

if __name__ == "__main__":
    fix_database()
