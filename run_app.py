"""
Glory2YahPub Application Runner
Uses the blueprint architecture
"""
import os
from app import create_app

# Set environment variables
os.environ['SECRET_KEY'] = 'glory2yah_secret_key_2024_secure_token_32chars_long'
os.environ['ADMIN_PASSWORD'] = 'admin123456'
os.environ['FLASK_ENV'] = 'development'

# Create the app using the factory
app = create_app()

if __name__ == '__main__':
    print("🎉 Glory2YahPub - Blueprint Architecture")
    print("🚀 Starting on http://127.0.0.1:8080")
    print("✅ All blueprints loaded!")
    print("📱 Modern UI: Facebook + TikTok + AliExpress Style")
    print("📊 2-Column Layout: POSTS (left) + ADS Carousel (right)")
    print("⏱️  Auto-slide carousel every 1 second")
    app.run(host='0.0.0.0', port=8080, debug=True)
