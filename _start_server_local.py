"""Robust local launcher. Patches Python's logging root handlers IMMEDIATELY so that
cp1252 UnicodeEncodeError on Windows never crashes boot, then launches Flask-SocketIO
(HTTP + WebSocket for KONFERANS module). Survives shell sessions by detaching.
"""
import os, sys, time, traceback

os.environ.setdefault('FLASK_ENV', 'development')
os.environ.setdefault('SECRET_KEY', 'glory2yah_secret_key_2024_secure_token_32chars_long')
os.environ.setdefault('ADMIN_WHATSAPP', '+50942882076')
os.environ.setdefault('ADMIN_PSEUDO',   '+50942882076')
os.environ.setdefault('ADMIN_PASSWORD', 'StanGlory2YahPub1986')
os.environ['PYTHONUNBUFFERED'] = '1'
os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'

# Force console I/O to UTF-8 surrogateescape to avoid UnicodeEncodeError on box-draw chars
for _n in ('stdout','stderr'):
    _stream = getattr(sys, _n, None)
    if _stream is None: continue
    try:
        import io as _io
        _buf = getattr(_stream, 'buffer', None)
        if _buf is None: continue
        _new = _io.TextIOWrapper(_buf, encoding='utf-8', errors='surrogateescape', line_buffering=True)
        setattr(sys, _n, _new)
    except Exception:
        pass

BASE = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, 'run_manual_app.log')
PID_FILE = os.path.join(LOG_DIR, 'run_pid.txt')

# ————— Patch ALL logging StreamHandler .emit() on ALL loggers BEFORE importing app —————
def _patch_logging_stream_handlers():
    import logging
    class SafeStreamHandler(logging.StreamHandler):
        def emit(self2, record):
            try:
                msg = self2.format(record) + self2.terminator
            except Exception:
                return
            stream = self2.stream
            try:
                if hasattr(stream, 'buffer'):
                    try:
                        stream.buffer.write(msg.encode('utf-8', errors='surrogateescape'))
                        stream.buffer.flush()
                        return
                    except Exception:
                        pass
                stream.write(msg)
                try: stream.flush()
                except Exception: pass
            except Exception:
                try:
                    with open(LOG_FILE, 'a', encoding='utf-8') as f:
                        f.write(msg)
                except Exception:
                    pass
    # Patch ALL existing stream handlers (root + werkzeug + flask + etc.)
    def _walk(h):
        for _ in range(3):
            try:
                if isinstance(h, logging.StreamHandler) and type(h) is logging.StreamHandler:
                    h.__class__ = SafeStreamHandler
                if hasattr(h, 'stream') and hasattr(h, 'emit'):
                    old = h.emit
                    def _em(self, r, _old=old, _sh=SafeStreamHandler.emit.__get__(self, type(self))):
                        try:
                            return _old(r)
                        except (UnicodeEncodeError, OSError):
                            return _sh(r)
                    h.emit = _em.__get__(h, type(h))
            except Exception:
                break

    for logger_name in (None, '', 'werkzeug', 'flask.app', 'flask.request', 'engineio', 'socketio'):
        lg = logging.getLogger(logger_name) if logger_name is not None else logging.getLogger()
        for h in list(lg.handlers): _walk(h)
_patch_logging_stream_handlers()

# Append boot separator
try:
    with open(LOG_FILE, 'a', encoding='utf-8') as _logf:
        _logf.write('\n' + '='*72 + '\n')
        _logf.write(f'--- boot {time.strftime("%Y-%m-%d %H:%M:%S")} pid={os.getpid()} ---\n')
except Exception:
    pass

try:
    from app import create_app, socketio
    app = create_app('development')
except Exception as e:
    tb = traceback.format_exc()
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f'[BOOT-ERROR] {type(e).__name__}: {e}\n{tb}\n')
    except Exception:
        pass
    sys.stderr.write(tb)
    raise

HOST = os.environ.get('HOST', '127.0.0.1')
PORT = int(os.environ.get('PORT', '5000'))

try:
    with open(PID_FILE, 'w') as pf:
        pf.write(str(os.getpid()))
except Exception:
    pass

# Print banners (UTF-8 safe)
SEP = '='*64
msg = f'\n{SEP}\n  GLORY2YAHPUB — LOKAL SERVER LANSE\n{SEP}\n'
msg += f'  URL      : http://{HOST}:{PORT}\n'
msg += f'  Konferans: ws://{HOST}:{PORT}/socket.io/\n'
msg += f'  async_mode= {socketio.async_mode}\n'
msg += f'  PID      : {os.getpid()}  -> {PID_FILE}\n'
msg += f'  LOG FILE : {LOG_FILE}\n{SEP}\n\n'
try:
    sys.stdout.write(msg); sys.stdout.flush()
except Exception:
    pass

try:
    socketio.run(app, host=HOST, port=PORT,
                 debug=False, use_reloader=False,
                 allow_unsafe_werkzeug=True,
                 log_output=False)
except KeyboardInterrupt:
    try:
        sys.stdout.write('\n[server] KeyboardInterrupt — done.\n'); sys.stdout.flush()
    except Exception:
        pass
except Exception as e:
    tb = traceback.format_exc()
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f'[SERVER-ERROR] {type(e).__name__}: {e}\n{tb}\n')
    except Exception:
        pass
    sys.stderr.write(tb)
    raise
