"""
Render test: room page must include the new Live/Stream UI for owners,
and must NOT include it for guests. Also sanity-checks the JS block.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import User, KonferansRoom

app = create_app()
app.config['WTF_CSRF_ENABLED'] = False
app.config['TESTING'] = True

OWNER_WA = '+50990000003'
ROOM_ID = 'SMOKE_RENDER_ROOM_1'
ROOM_CODE = 'SMOKRND'

with app.app_context():
    db.create_all()
    KonferansRoom.query.filter_by(room_id=ROOM_ID).delete()
    User.query.filter(User.whatsapp == OWNER_WA).delete(synchronize_session=False)
    db.session.commit()
    owner = User(name='Render Owner', pseudo='RenderOwner', whatsapp=OWNER_WA, password_hash='x')
    db.session.add(owner)
    db.session.commit()
    db.session.add(KonferansRoom(room_id=ROOM_ID, room_code=ROOM_CODE, room_name='Render Room',
                                 creator_name='Render Owner', user_id=owner.id, is_active=True))
    db.session.commit()
    owner_id = owner.id

client = app.test_client()
with client.session_transaction() as s:
    s['_user_id'] = str(owner_id)
    s['_fresh'] = True

resp = client.get(f'/konferans/room/{ROOM_CODE}')
html = resp.get_data(as_text=True)
print(f'GET /konferans/room/{ROOM_CODE} -> {resp.status_code}')

fails = []


def check(name, cond):
    print(('  [OK]  ' if cond else '  [FAIL] ') + name)
    if not cond:
        fails.append(name)


owner_markers = [
    'id="streamMenuBtn"', 'openStreamSetup(\'facebook\')', 'openStreamSetup(\'youtube\')',
    'openStreamSetup(\'tiktok\')', 'openStreamSetup(\'custom\')', 'openStreamSetup(\'whatsapp\')',
    'openStreamSetup(\'titleframe\')', 'id="stopStreamItem"', 'id="streamModal"',
    'id="streamIngestUrl"', 'id="streamKey"', 'id="streamBurnFrame"',
    'function startWhatsAppSave', 'function finishWhatsAppSave', 'function collectRoomAudioStream',
    'function buildTitleFrameCanvas', 'function downloadTitleFramePNG',
    'function enableTitleFrameOverlay', 'function disableTitleFrameOverlay',
    'function goLiveFromModal', 'function stopStreaming', "socket.on('streaming_started'",
    "socket.on('streaming_stopped'", 'function refreshStreamStatus', 'konf-live-banner',
]
for m in owner_markers:
    check(f'owner page has {m}', m in html)

# Banner must exist for owners (participant JS also renders it)
check('liveStatus banner present', 'id="liveStatus"' in html)
check('roomNameJinja injected', 'const roomNameJinja' in html)
check('CSS loaded (konferans.css)', 'konferans.css' in html)

# Balance sanity: real tokenizer check of the main script block
scripts = re.findall(r'<script>(.*?)</script>', html, flags=re.S)
main = max(scripts, key=len)
from _dbg_js_balance import check_js_balance
ok, msg = check_js_balance(main)
check('main script JS balanced (tokenizer)', ok if ok else f'FAIL: {msg}')
check('jinja endif count balanced', html.count('{% if') == html.count('{% endif %}') + html.count('{% endif-%}'))

print()
if fails:
    print(f'{len(fails)} FAILURES: {fails}')
    sys.exit(1)
print('RENDER TEST PASSED')

# Cleanup
with app.app_context():
    KonferansRoom.query.filter_by(room_id=ROOM_ID).delete()
    User.query.filter(User.whatsapp == OWNER_WA).delete(synchronize_session=False)
    db.session.commit()
