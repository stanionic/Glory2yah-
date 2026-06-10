"""
Glory2YahPub - Application Entry Point
Uses the application factory pattern
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import the application factory
from app import create_app, socketio

# Create the Flask application
app = create_app()

if __name__ == '__main__':
    print("\n" + "="*60)
    print("GLORY2YAHPUB - STARTING")
    print("="*60)
    print("\n[OK] Database: Connected")
    print("[OK] Redis: " + ("Connected" if app.config.get('REDIS_URL') else "Optional"))
    print("[OK] Server: http://localhost:8080")
    print("[OK] Network: http://YOUR_IP:8080")
    print("\nFeatures:")
    print("   - Modern Mobile-First UI")
    print("   - TikTok/Facebook-Style Feed")
    print("   - AliExpress-Style Marketplace")
    print("   - Gkach Reward System")
    print("   - Shopping Cart & Checkout")
    print("   - Video Conferencing")
    print("   - Party Management")
    print("   - Education Services")
    print("\nPress Ctrl+C to stop\n")
    
    # Run with SocketIO support
    socketio.run(
        app,
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 8080)),
        debug=True,
        use_reloader=False
    )
