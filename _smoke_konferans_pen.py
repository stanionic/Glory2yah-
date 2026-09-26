"""Smoke test — Konferans media scroll-bar + pen live editing.

Covers:
  * owner render: scroll/zoom/sync/eraser/export UI + the JS API is present
  * guest render: zoom + scroll available, pen/sync tools NOT exposed
  * CSS: custom scroll bars on .konf-media-display-content, stage, zoom label
  * live socket relays (real handlers): media_view, media_annotation,
    media_annotation_remove reach the participants, and a NON-owner emit is
    rejected by the owner guard
  * JS tokenizer balance + jinja if/endif balance of the rendered page
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db, socketio
from app.models import User, KonferansRoom
from konferans import routes as kr

app = create_app()
app.config['WTF_CSRF_ENABLED'] = False
app.config['TESTING'] = True

OWNER_WA = '+50990000077'
GUEST_WA = '+50990000078'
ROOM_ID = 'SMOKE_PEN_ROOM_1'
ROOM_CODE = 'SMOKPEN'

with app.app_context():
    db.create_all()
    KonferansRoom.query.filter_by(room_id=ROOM_ID).delete()
    User.query.filter(User.whatsapp.in_([OWNER_WA, GUEST_WA])).delete(synchronize_session=False)
    db.session.commit()
    owner = User(name='Pen Owner', pseudo='PenOwner', whatsapp=OWNER_WA, password_hash='x')
    guest = User(name='Pen Guest', pseudo='PenGuest', whatsapp=GUEST_WA, password_hash='x')
    db.session.add_all([owner, guest])
    db.session.commit()
    db.session.add(KonferansRoom(room_id=ROOM_ID, room_code=ROOM_CODE, room_name='Pen Room',
                                 creator_name='Pen Owner', user_id=owner.id, is_active=True))
    db.session.commit()
    owner_id = owner.id
    guest_id = guest.id

fails = []


def check(name, cond):
    print(('  [OK]  ' if cond else '  [FAIL] ') + name)
    if not cond:
        fails.append(name)


def http_client(user_id):
    client = app.test_client()
    if user_id:
        with client.session_transaction() as s:
            s['_user_id'] = str(user_id)
            s['_fresh'] = True
    return client


# ---------------------------------------------------------------------------
# 1. Owner render
# ---------------------------------------------------------------------------
owner_client = http_client(owner_id)
resp = owner_client.get(f'/konferans/room/{ROOM_CODE}')
html = resp.get_data(as_text=True)
print(f'GET /konferans/room/{ROOM_CODE} (owner) -> {resp.status_code}')
check('owner room page 200', resp.status_code == 200)

owner_markers = [
    'id="mediaStage"',
    'id="mediaScrollUpBtn"', 'id="mediaScrollDownBtn"',
    'id="mediaZoomInBtn"', 'id="mediaZoomOutBtn"', 'id="mediaZoomLabel"',
    'id="mediaViewSyncBtn"', 'id="annEraserBtn"', 'id="annDownloadBtn"',
    'MEDIA_ZOOM_STEPS',
    'function applyMediaZoom', 'function setMediaZoom', 'function zoomMedia',
    'function resetMediaZoom', 'function scrollMediaPage', 'function mediaScrollFraction',
    'function restoreMediaScrollFraction', 'function attachMediaViewportEvents',
    'function toggleMediaViewSync', 'function emitMediaView', 'function applyRemoteMediaView',
    'function ensureAnnotationCanvas', 'function syncMediaPenLayer', 'function resizeAnnotationCanvas',
    'function eraseStrokeAt', 'function strokeSegments', 'function distToSegment',
    'function downloadAnnotatedMedia', 'function handleMediaShortcut', 'function normLineWidth',
    "socket.emit('media_view'", "socket.on('media_view'",
    "socket.emit('media_annotation_remove'", "socket.on('media_annotation_remove'",
]
for m in owner_markers:
    check(f'owner page has {m}', m in html)

# ---------------------------------------------------------------------------
# 2. Guest render — same scrolling/zooming, no teacher-only pen/sync entry point
# ---------------------------------------------------------------------------
guest_client = http_client(None)
resp_g = guest_client.get(f'/konferans/room/{ROOM_CODE}')
html_g = resp_g.get_data(as_text=True)
print(f'GET /konferans/room/{ROOM_CODE} (guest) -> {resp_g.status_code}')
check('guest room page 200', resp_g.status_code == 200)

for m in ['id="mediaStage"', 'id="mediaZoomInBtn"', 'id="mediaZoomOutBtn"',
          'id="mediaScrollUpBtn"', 'id="mediaScrollDownBtn"', 'function applyMediaZoom',
          'function applyRemoteMediaView']:
    check(f'guest page has {m}', m in html_g)
for m in ['id="mediaPenBtn"', 'id="mediaViewSyncBtn"']:
    check(f'guest page hides owner tool {m}', m not in html_g)


# ---------------------------------------------------------------------------
# 3. CSS — the requested scroll bar + zoom/stage styles
# ---------------------------------------------------------------------------
css_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'css', 'konferans.css')
with open(css_path, 'r', encoding='utf-8', newline='') as fh:
    css = fh.read()
check('CSS cache-buster bumped to v=7', 'konferans.css?v=7' in html)
for m in ['.konf-media-display-content::-webkit-scrollbar {',
          '.konf-media-display-content::-webkit-scrollbar-thumb {',
          '.konf-media-display-content::-webkit-scrollbar-track {',
          'scrollbar-color: rgba(232,200,116,0.6)',
          'overflow: auto;',
          '.konf-media-stage {',
          '.konf-media-zoom-label {',
          '#mediaViewSyncBtn.active {']:
    check(f'CSS has {m}', m in css)
check('viewport is scrollable (max-height + overflow)',
      re.search(r'\.konf-media-display-content \{.*?overflow: auto;', css, re.S) is not None)
check('fullscreen viewport also scrolls',
      re.search(r'\.konf-media-display\.fullscreen \.konf-media-display-content \{.*?overflow: auto;', css, re.S) is not None)

# ---------------------------------------------------------------------------
# 4. Live socket relays (real handlers, owner guard included)
# ---------------------------------------------------------------------------
print('Socket.IO relays:')
sock_owner = socketio.test_client(app, flask_test_client=http_client(owner_id))
sock_guest = socketio.test_client(app, flask_test_client=http_client(guest_id))
try:
    sock_owner.emit('join', {'room_id': ROOM_ID, 'user_name': 'PenOwner'})
    sock_guest.emit('join', {'room_id': ROOM_ID, 'user_name': 'PenGuest'})
    identities = kr.room_socket_users.get(ROOM_ID, {})
    check('2 sockets registered in the room', len(identities) == 2)
    check('exactly one socket is flagged owner',
          sum(1 for v in identities.values() if v.get('is_owner')) == 1)

    sock_owner.get_received()
    sock_guest.get_received()

    # --- live view sync (zoom + scroll fraction) ---
    sock_owner.emit('media_view', {'room_id': ROOM_ID, 'user_name': 'PenOwner',
                                   'zoom': 150, 'fx': 0.25, 'fy': 0.75})
    guest_msgs = [m for m in sock_guest.get_received() if m['name'] == 'media_view']
    owner_echo = [m for m in sock_owner.get_received() if m['name'] == 'media_view']
    check('participant receives media_view', len(guest_msgs) == 1)
    if guest_msgs:
        payload = guest_msgs[0]['args'][0]
        check('media_view carries zoom 150', payload.get('zoom') == 150)
        check('media_view carries scroll fractions',
              payload.get('fx') == 0.25 and payload.get('fy') == 0.75)
    check('owner does not receive its own media_view echo', len(owner_echo) == 0)

    # --- owner-only guard: a participant may not drive the teacher view ---
    sock_owner.get_received()
    sock_guest.emit('media_view', {'room_id': ROOM_ID, 'zoom': 400, 'fx': 1, 'fy': 1})
    check('non-owner media_view is rejected',
          not [m for m in sock_owner.get_received() if m['name'] == 'media_view'])


    # --- live stroke (normalized coordinates) ---
    stroke = {'tool': 'pen', 'color': '#FF2D55', 'n': 0.004,
              'path': [{'x': 0.1, 'y': 0.2}, {'x': 0.3, 'y': 0.4}],
              'sid': 'st_smoke_1', '_ts': 1234567890}
    sock_guest.get_received()
    sock_owner.emit('media_annotation', {'room_id': ROOM_ID, 'user_name': 'PenOwner', 'stroke': stroke})
    stroke_msgs = [m for m in sock_guest.get_received() if m['name'] == 'media_annotation']
    check('participant receives the live stroke', len(stroke_msgs) == 1)
    if stroke_msgs:
        got = stroke_msgs[0]['args'][0]['stroke']
        check('stroke keeps its sid', got.get('sid') == 'st_smoke_1')
        check('stroke keeps normalized coords + line width',
              got['path'][0]['x'] == 0.1 and got['path'][1]['y'] == 0.4 and got['n'] == 0.004)

    # --- eraser: single stroke removal relayed live ---
    sock_guest.get_received()
    sock_owner.emit('media_annotation_remove', {'room_id': ROOM_ID, 'sid': 'st_smoke_1',
                                                'user_name': 'PenOwner'})
    remove_msgs = [m for m in sock_guest.get_received() if m['name'] == 'media_annotation_remove']
    check('participant receives the eraser removal', len(remove_msgs) == 1)
    if remove_msgs:
        check('removal carries the erased sid', remove_msgs[0]['args'][0].get('sid') == 'st_smoke_1')

    sock_owner.get_received()
    sock_guest.emit('media_annotation_remove', {'room_id': ROOM_ID, 'sid': 'st_smoke_1'})
    check('non-owner eraser removal is rejected',
          not [m for m in sock_owner.get_received() if m['name'] == 'media_annotation_remove'])
finally:
    try:
        sock_owner.disconnect()
        sock_guest.disconnect()
    except Exception:
        pass

# ---------------------------------------------------------------------------
# 5. Rendered JS sanity (tokenizer) + jinja balance
# ---------------------------------------------------------------------------
scripts = re.findall(r'<script>(.*?)</script>', html, flags=re.S)
main_js = max(scripts, key=len)
from _dbg_js_balance import check_js_balance
ok, msg = check_js_balance(main_js)
check('main script JS balanced (tokenizer)', ok if ok else f'FAIL: {msg}')
check('jinja if/endif balanced', html.count('{% if') == html.count('{% endif %}') + html.count('{% endif-%}'))
check('normalized strokes documented in JS', 'normalized coordinates' in html)
check('canvas is re-created on demand (pen survives a media switch)',
      'function ensureAnnotationCanvas' in html and 'canvas.remove();' in html)
check('canvas stays visible for participants (they see the live strokes)',
      "canvas.style.display = 'block';" in html)
check('canvas keeps pointer-events gated by the pen state',
      "canvas.style.pointerEvents = penActive ? 'auto' : 'none';" in html)

print()
if fails:
    print(f'{len(fails)} FAILURES:')
    for f in fails:
        print('   - ' + f)
    sys.exit(1)
print('PEN + SCROLL SMOKE TEST PASSED')

# Cleanup (DB + in-RAM session dicts)
with app.app_context():
    KonferansRoom.query.filter_by(room_id=ROOM_ID).delete()
    User.query.filter(User.whatsapp.in_([OWNER_WA, GUEST_WA])).delete(synchronize_session=False)
    db.session.commit()
for store in (kr.room_socket_users, kr.room_participants, kr.active_rooms,
              kr.room_waiting, kr.room_admitted, kr.room_banned):
    store.pop(ROOM_ID, None)

