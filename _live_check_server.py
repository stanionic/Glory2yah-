"""Live check: is the running Glory2YahPub server serving HTTP + Socket.IO/WebSocket?

Usage (server already running, PORT from .env or argument):
    venv\\Scripts\\python.exe _live_check_server.py [port]

Checks
  1. HTTP 200 on / and on the patched konferans.css (v=7)
  2. Engine.IO polling handshake on /socket.io/?EIO=4&transport=polling -> open packet with sid
  3. Real WebSocket connection through python-socketio (transport == 'websocket')
     — this is the transport Konferans uses for live zoom/scroll + pen strokes.
"""
import os
import re
import sys

import requests
import socketio

PORT = sys.argv[1] if len(sys.argv) > 1 else os.environ.get('PORT', '8080')
BASE = f'http://127.0.0.1:{PORT}'

fails = []


def check(name, cond, extra=''):
    print(('  [OK]  ' if cond else '  [FAIL] ') + name + (f'  {extra}' if extra else ''))
    if not cond:
        fails.append(name)


# --- 1. HTTP ---------------------------------------------------------------
try:
    r = requests.get(BASE + '/', timeout=20)
    check('GET / -> 200', r.status_code == 200, f'({len(r.content)} bytes)')
except Exception as exc:
    check('GET / -> 200', False, f'({exc})')

try:
    r = requests.get(BASE + '/static/css/konferans.css?v=7', timeout=20)
    check('GET /static/css/konferans.css?v=7 -> 200', r.status_code == 200,
          f'({len(r.content)} bytes)')
    check('served CSS is the scroll/pen build (konf-media-stage)', '.konf-media-stage' in r.text)
    check('served CSS has the gold scroll bar',
          'scrollbar-color: rgba(232,200,116,0.6)' in r.text)
except Exception as exc:
    check('GET /static/css/konferans.css?v=7 -> 200', False, f'({exc})')

# --- 2. Engine.IO polling handshake ---------------------------------------
try:
    r = requests.get(BASE + '/socket.io/', params={'EIO': '4', 'transport': 'polling'},
                     timeout=20)
    body = r.text
    m = re.search(r'"sid"\s*:\s*"([^"]+)"', body)
    check('socket.io polling handshake -> 200', r.status_code == 200, body[:60])
    check('handshake returns an engine.io sid', bool(m), m.group(1) if m else '')
    check('engine.io open packet (0{...})', body.startswith('0{'), body[:20])
except Exception as exc:
    check('socket.io polling handshake -> 200', False, f'({exc})')

# --- 3. Real WebSocket transport ------------------------------------------
sio = socketio.Client(reconnection=False, request_timeout=15)
state = {}


@sio.event
def connect():
    state['connected'] = True
    state['transport'] = getattr(sio, 'transport', lambda: '?')() if callable(
        getattr(sio, 'transport', None)) else '?'


try:
    sio.connect(BASE, transports=['websocket'], wait_timeout=15)
    check('websocket transport connected', state.get('connected') is True,
          f'transport={state.get("transport")}')
    check('transport is really websocket', state.get('transport') in (None, 'websocket'))
    check('client has a sid', bool(sio.sid), str(sio.sid))
except Exception as exc:
    check('websocket transport connected', False, f'({exc})')
finally:
    try:
        sio.disconnect()
    except Exception:
        pass

print()
if fails:
    print(f'{len(fails)} FAILURE(S): ' + ', '.join(fails))
    sys.exit(1)
print('LIVE SERVER CHECK PASSED (HTTP + Socket.IO/WebSocket)')
