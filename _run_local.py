"""Local dev launcher: runs the Flask app through Flask-SocketIO so the
konferans websocket endpoints work too. Scratch file, not used in prod."""
import os
import sys

os.environ.setdefault('FLASK_ENV', 'development')
os.environ['PYTHONUNBUFFERED'] = '1'
os.environ['PYTHONIOENCODING'] = 'utf-8'

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, socketio

app = create_app('development')

if __name__ == '__main__':
    host = os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('LOCAL_PORT', 5000))
    print(f'>>> serving on http://{host}:{port} (async_mode={socketio.async_mode})', flush=True)
    socketio.run(app, host=host, port=port, debug=False, use_reloader=False,
                 allow_unsafe_werkzeug=True)
