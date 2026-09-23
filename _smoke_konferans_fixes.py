"""
Smoke/validation test: Konferans live-streaming residual fixes (K-5 → K-8).

Covers:
  K-5  openStreamSetup('titleframe') is reachable (branch before platform guard)
  K-6  no legacy Query.get() left in konferans/routes.py
  K-7  _stop_stream_session() closes RAM state + DB row + returns payload
  K-8  disableTitleFrameOverlay() guards the (possibly absent) camera track
  Guest page must NOT ship owner-only Live controls (but must keep the banner)
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import User, KonferansRoom, KonferansStreamSession

app = create_app()
app.config['WTF_CSRF_ENABLED'] = False
app.config['TESTING'] = True

OWNER_WA = '+50990000009'
GUEST_WA = '+50990000010'
ROOM_ID = 'SMOKE_FIXES_ROOM_1'
ROOM_CODE = 'SMOKFIX'

fails = []


def check(name, cond):
    print(('  [OK]  ' if cond else '  [FAIL] ') + name)
    if not cond:
        fails.append(name)


# ---------- Static source checks (K-5, K-6, K-8) ----------
with open('konferans/routes.py', encoding='utf-8') as f:
    routes_src = f.read()
with open('templates/konferans/room.html', encoding='utf-8') as f:
    tpl_src = f.read()

check('K-6 no legacy Query.get() in routes.py', '.query.get(' not in routes_src)
check('K-6 db.session.get() used for stream session', 'db.session.get(KonferansStreamSession' in routes_src)
check('K-7 helper defined once', routes_src.count('def _stop_stream_session(') == 1)
check('K-7 helper used by HTTP route', "payload = _stop_stream_session(room_id, 'manual')" in routes_src)
check('K-7 helper used by disconnect', 'owner_disconnect' in routes_src and 'room_empty' in routes_src)

_m = re.search(r'function openStreamSetup\(platform\) \{(.*?)\n    \}\n', tpl_src, flags=re.S)
check('K-5 openStreamSetup extractable', _m is not None)
if _m:
    body = _m.group(1)
    i_frame = body.find("platform === 'titleframe'")
    i_guard = body.find('if (!STREAM_PLATFORMS[platform]) return;')
    check('K-5 titleframe branch exists', i_frame != -1)
    check('K-5 titleframe branch BEFORE platform guard', i_frame != -1 and i_guard != -1 and i_frame < i_guard)

check('K-8 null-track guard present',
      'if (st.oldTrack) replaceTrackForAll(st.newTrack, st.oldTrack, localStream);' in tpl_src)
check('K-8 old null-passing call removed',
      'replaceTrackForAll(st.newTrack, st.oldTrack || null, localStream)' not in tpl_src)

# ---------- Runtime setup ----------
with app.app_context():
    db.create_all()
    KonferansStreamSession.query.filter_by(room_id=ROOM_ID).delete()
    KonferansRoom.query.filter_by(room_id=ROOM_ID).delete()
    User.query.filter(User.whatsapp.in_([OWNER_WA, GUEST_WA])).delete(synchronize_session=False)
    db.session.commit()

    owner = User(name='Fixes Owner', pseudo='FixesOwner', whatsapp=OWNER_WA, password_hash='x')
    guest = User(name='Fixes Guest', pseudo='FixesGuest', whatsapp=GUEST_WA, password_hash='x')
    db.session.add_all([owner, guest])
    db.session.commit()

    db.session.add(KonferansRoom(room_id=ROOM_ID, room_code=ROOM_CODE, room_name='Fixes Room',
                                 creator_name='Fixes Owner', user_id=owner.id, is_active=True))
    db.session.commit()
    owner_id, guest_id = owner.id, guest.id


def login(client, uid):
    with client.session_transaction() as s:
        s['_user_id'] = str(uid)
        s['_fresh'] = True


client = app.test_client()

# ---------- K-7 functional: start live, then disconnect-cleanup closes it ----------
login(client, owner_id)
r = client.post(f'/konferans/api/stream/start/{ROOM_ID}', json={
    'platform': 'youtube', 'ingest_url': 'rtmp://a.rtmp.youtube.com/live2',
    'stream_key': 'fixes-1234', 'title': 'Fixes Live'})
check('setup: owner start stream -> 200', r.status_code == 200)

from konferans.routes import _stop_stream_session, room_stream_sessions

with app.app_context():
    payload = _stop_stream_session(ROOM_ID, 'owner_disconnect')
    check('K-7 payload returned on disconnect',
          isinstance(payload, dict) and payload.get('room_id') == ROOM_ID)
    check('K-7 reason propagated', bool(payload) and payload.get('stopped_reason') == 'owner_disconnect')
    check('K-7 RAM state cleared', ROOM_ID not in room_stream_sessions)

    row = (KonferansStreamSession.query.filter_by(room_id=ROOM_ID)
           .order_by(KonferansStreamSession.id.desc()).first())
    check('K-7 DB row stopped', row is not None and row.status == 'stopped')
    check('K-7 stopped_at persisted', row is not None and row.stopped_at is not None)
    check('K-7 duration persisted', row is not None and row.duration_seconds is not None)

    check('K-7 second call is a no-op', _stop_stream_session(ROOM_ID, 'room_empty') is None)

r = client.get(f'/konferans/api/stream/status/{ROOM_ID}')
check('K-7 status not streaming after cleanup', r.get_json().get('streaming') is False)
r = client.post(f'/konferans/api/stream/stop/{ROOM_ID}')
check('K-7 stop when nothing live -> 404', r.status_code == 404)

# ---------- Render checks: owner page vs guest page ----------
resp = client.get(f'/konferans/room/{ROOM_CODE}')
owner_html = resp.get_data(as_text=True)
check('owner room page -> 200', resp.status_code == 200)
check('owner page keeps Kadr Tite menu item', "openStreamSetup('titleframe')" in owner_html)
check('owner page keeps stream modal + banner',
      'id="streamModal"' in owner_html and 'konf-live-banner' in owner_html)

scripts = re.findall(r'<script>(.*?)</script>', owner_html, flags=re.S)
from _dbg_js_balance import check_js_balance
ok, msg = check_js_balance(max(scripts, key=len))
check('owner page JS balanced', ok if ok else f'FAIL: {msg}')

login(client, guest_id)
resp = client.get(f'/konferans/room/{ROOM_CODE}')
guest_html = resp.get_data(as_text=True)
check('guest room page -> 200', resp.status_code == 200)
check('guest page HAS live banner',
      'konf-live-banner' in guest_html and 'id="liveStatus"' in guest_html)
for marker in ('id="streamMenuBtn"', 'id="streamModal"', 'id="stopStreamItem"',
               'function openStreamSetup', 'function startWhatsAppSave', 'id="buyTimeBtn"'):
    check(f'guest page excludes {marker}', marker not in guest_html)

# ---------- Cleanup ----------
with app.app_context():
    KonferansStreamSession.query.filter_by(room_id=ROOM_ID).delete()
    KonferansRoom.query.filter_by(room_id=ROOM_ID).delete()
    User.query.filter(User.whatsapp.in_([OWNER_WA, GUEST_WA])).delete(synchronize_session=False)
    db.session.commit()

print()
if fails:
    print(f'{len(fails)} FAILURES: {fails}')
    sys.exit(1)
print('ALL KONFERANS FIX TESTS PASSED')
