import logging
logging.disable(logging.CRITICAL)
from app import create_app
import app as appmod
app = appmod.app
sio = appmod.socketio

server = sio.server
print("server type:", type(server).__name__)
h = getattr(server, 'handlers', None)
print("server.handlers:", type(h).__name__)
if isinstance(h, dict):
    for ns, ev in h.items():
        print("NS:", repr(ns), "EVENTS:", sorted(k for k in ev if not str(k).startswith('_')))
