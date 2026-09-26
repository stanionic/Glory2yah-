import os
import sys

os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
os.environ['PYTHONUNBUFFERED'] = '1'
os.environ['PYTHONIOENCODING'] = 'utf-8'

class _SafeStream:
    def __init__(self, real):
        self.real = real
        self.encoding = 'utf-8'
    def write(self, s):
        try:
            self.real.write(s)
        except Exception:
            try:
                self.real.buffer.write(s.encode('utf-8', errors='replace'))
            except Exception:
                pass
    def writelines(self, lines):
        for ln in lines:
            self.write(ln)
    def flush(self):
        try: self.real.flush()
        except Exception: pass
    def isatty(self):
        try: return self.real.isatty()
        except Exception: return False

sys.stdout = _SafeStream(sys.stdout)
sys.stderr = _SafeStream(sys.stderr)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logging
_root_log = logging.getLogger()
for _h in list(_root_log.handlers):
    if hasattr(_h, 'stream') and _h.stream in (sys.__stdout__, sys.__stderr__):
        try:
            class _SF(logging.StreamHandler):
                def emit(self2, record):
                    try:
                        msg = self2.format(record) + self2.terminator
                        sys.stdout.write(msg)
                        sys.stdout.flush()
                    except Exception:
                        pass
            _new = _SF()
            _new.setLevel(_h.level)
            _new.setFormatter(_h.formatter)
            _root_log.handlers.remove(_h)
            _root_log.handlers.append(_new)
        except Exception:
            pass

from app import create_app, db

app = create_app(os.environ.get('FLASK_ENV', 'development'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '127.0.0.1')
    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
