
"""
Simple script to start the Glory2YahPub server
"""
import os

# Set environment variables
os.environ['SECRET_KEY'] = 'glory2yah_secret_key_2024_secure_token_32chars_long'
os.environ['ADMIN_PASSWORD'] = 'admin123456'
os.environ['FLASK_ENV'] = 'development'

# Import and create app
print("Creating application...")
from app import create_app
app = create_app()
print("Application created successfully!")

# Run the server
print("Starting server on http://localhost:8080...")
print("Test user credentials:")
print("  WhatsApp/Pseudo: +50912345678 or testuser")
print("  Password: 123456")

if __name__ == '__main__':
    try:
        app.run(
            host='0.0.0.0',
            port=8080,
            debug=True,
            use_reloader=False
        )
    except Exception as e:
        print(f"Error starting server: {e}")
        import traceback
        traceback.print_exc()
