import os
from app import create_app

# P1 FIX: NE JAMAIS hardcoder SECRET_KEY ni ADMIN_PASSWORD ici en PRODUCTION.
# simple_start.py = lanceur DEV LOCAL uniquement.
# En production, utilisez gunicorn + .env / variables d'environnement.
if not os.environ.get('SECRET_KEY'):
    try:
        import secrets
        fallback_path = os.path.join(os.path.dirname(__file__), '.flask_secret_key')
        if os.path.exists(fallback_path):
            with open(fallback_path, 'r', encoding='utf-8') as f:
                os.environ['SECRET_KEY'] = f.read().strip()
        else:
            _key = secrets.token_urlsafe(48)
            try:
                with open(fallback_path, 'w', encoding='utf-8') as f:
                    f.write(_key)
            except Exception:
                pass
            os.environ['SECRET_KEY'] = _key
    except Exception:
        import uuid
        os.environ['SECRET_KEY'] = uuid.uuid4().hex + uuid.uuid4().hex

if not os.environ.get('FLASK_ENV'):
    os.environ['FLASK_ENV'] = 'development'

app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True, use_reloader=False)
