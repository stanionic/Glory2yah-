"""KONFERANS real-time reproducibility probe.

Opens N Socket.IO clients (long-polling) against a running server, then checks that
ordinary HTTP requests are still answered. Used to compare gunicorn configurations:

    gunicorn app:app --bind 127.0.0.1:5055 --workers 4 --worker-class sync     # render.yaml today
    python tools/konferans_realtime_probe.py http://127.0.0.1:5055 8

Needs: pip install "python-socketio[client]==5.9.0" websocket-client requests
Result on the repo's configuration (4 sync workers, no Redis): 2/8 clients connect and
plain requests time out. Result with 1 gthread worker: 8/8 and no timeouts.
Run it against a STAGING copy of any new start command before deploying it.
"""
import sys, time, threading, requests, socketio
base, n = sys.argv[1], int(sys.argv[2])
clients, errs = [], []
def conn(i):
    c = socketio.Client(reconnection=False, request_timeout=8)
    try:
        c.connect(base, transports=['polling'], wait_timeout=8)
        clients.append(c)
    except Exception as e:
        errs.append(type(e).__name__)
ts = [threading.Thread(target=conn, args=(i,)) for i in range(n)]
t0 = time.time(); [t.start() for t in ts]; [t.join() for t in ts]
print(f"socket clients connected: {len(clients)}/{n}  failures: {len(errs)} {sorted(set(errs))[:2]}  ({time.time()-t0:.1f}s)")
time.sleep(3)
ok = slow = 0; lat = []
for _ in range(6):
    s = time.time()
    try:
        r = requests.get(base + '/health', timeout=6); ok += (r.status_code < 500)
    except Exception:
        slow += 1
    lat.append(round(time.time() - s, 2))
print(f"plain HTTP GET /health while {len(clients)} sockets are open: ok={ok}/6 timeouts={slow}  latencies={lat}")
alive = sum(1 for c in clients if c.connected)
print(f"sockets still connected after 3s: {alive}/{len(clients)}")
for c in clients:
    try: c.disconnect()
    except Exception: pass
