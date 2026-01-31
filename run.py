"""
CampusIQ - Application Entry Point
Run the Flask application
"""
import os
from dotenv import load_dotenv

# Load environment variables BEFORE importing the app or config
load_dotenv()

# Debugging
print(f"DEBUG: GOOGLE_CLIENT_ID loaded: {bool(os.environ.get('GOOGLE_CLIENT_ID'))}")
print(f"DEBUG: GEMINI_MODEL: {os.environ.get('GEMINI_MODEL')}")

from app import create_app

# Create the Flask application
app = create_app(os.environ.get('FLASK_ENV', 'development'))

if __name__ == '__main__':
    # Development server
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'true').lower() == 'true'
    
    print(f"""
    ╔═══════════════════════════════════════════════════════════╗
    ║                                                           ║
    ║   🎓 CampusIQ - Intelligent College Management System    ║
    ║                                                           ║
    ║   Server running at: http://localhost:{port}              ║
    ║   API Docs: http://localhost:{port}/api/docs              ║
    ║   Health Check: http://localhost:{port}/health            ║
    ║                                                           ║
    ╚═══════════════════════════════════════════════════════════╝
    """)
    
    app.run(host='0.0.0.0', port=port, debug=debug)
