
import os
import sys
from sqlalchemy import create_engine, text
from app.config import config

def check_connection():
    env_name = os.environ.get('FLASK_ENV', 'development')
    print(f"Checking database connection for environment: {env_name}")
    
    app_config = config[env_name]
    
    # Manually determine URI based on logic in config.py since we aren't instantiating the full Flask app
    uri = None
    
    if env_name == 'development':
        use_sqlite = os.environ.get('USE_SQLITE', 'true').lower() == 'true'
        if use_sqlite:
            uri = 'sqlite:///campusiq_dev.db'
            print("Configuration says: Using SQLite (Development)")
        else:
            uri = app_config.SQLALCHEMY_DATABASE_URI
            print(f"Configuration says: Using Oracle via {os.environ.get('ORACLE_DSN')}")

    elif env_name == 'production':
         uri = os.environ.get('DATABASE_URL')
         if not uri:
             uri = app_config.SQLALCHEMY_DATABASE_URI
             print("Configuration says: Using Default Oracle (Production fallback)")
         else:
             print("Configuration says: Using DATABASE_URL (Likely Postgres or external)")

    if not uri:
        # Fallback
        uri = 'sqlite:///campusiq_dev.db'
        print("Warning: No URI found, defaulting to SQLite check.")

    print(f"Attempting to connect to: {uri}")

    try:
        engine = create_engine(uri)
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            print("✅ CONNECTION SUCCESSFUL!")
            print(f"DB Response: {result.fetchone()}")
    except Exception as e:
        print("❌ CONNECTION FAILED")
        print(f"Error: {str(e)}")
        if "psycopg2" in str(e) or "No module named 'psycopg2'" in str(e):
             print("\n⚠️  MISSING DRIVER: It looks like you are trying to connect to Postgres but 'psycopg2-binary' is not installed.")

if __name__ == "__main__":
    check_connection()
