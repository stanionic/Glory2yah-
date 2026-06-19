
import os
from app import create_app

os.environ['SECRET_KEY'] = 'glory2yah_secret_key_2024_secure_token_32chars_long'
os.environ['ADMIN_PASSWORD'] = 'admin123456'
os.environ['FLASK_ENV'] = 'development'

app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True, use_reloader=False)
