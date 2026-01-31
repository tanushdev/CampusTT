
import os
import uuid
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

def migrate():
    uri = os.environ.get('DATABASE_URL')
    if not uri:
        print("Error: DATABASE_URL not found in environment")
        return

    print(f"Connecting to database...")
    engine = create_engine(uri)
    
    with engine.connect() as conn:
        print("Creating import_progress table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS import_progress (
                college_id UUID PRIMARY KEY,
                total_rows INTEGER DEFAULT 0,
                processed_rows INTEGER DEFAULT 0,
                status VARCHAR(20) DEFAULT 'idle',
                message TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        # Check if indexes already exist or add them
        print("Checking indexes...")
        try:
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_schedules_day_time ON schedules (day_of_week, start_time)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_schedules_class_code ON schedules (class_code)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_schedules_instructor_name ON schedules (instructor_name)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_schedules_room_code ON schedules (room_code)"))
        except Exception as e:
            print(f"Index notice (may already exist): {e}")
            
        conn.commit()
        print("✅ Migration successful!")

if __name__ == "__main__":
    migrate()
