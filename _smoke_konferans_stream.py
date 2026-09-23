"""
Smoke test: Konferans live-streaming features.
Covers: /api/stream/start, /api/stream/status, /api/stream/stop,
permissions (owner vs guest), duplicate start, recording title column.
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import User, KonferansRoom, KonferansRecording, KonferansStreamSession

app = create_app()
app.config['WTF_CSRF_ENABLED'] = False
app.config['TESTING'] = True

OWNER_WA = '+50990000001'
GUEST_WA = '+50990000002'
ROOM_ID = 'SMOKE_STREAM_ROOM_1'

fails = []


def check(name, cond):
    print(('  [OK]  ' if cond else '  [FAIL] ') + name)
    if not cond:
        fails.append(name)


with app.app_context():
    db.create_all()
    KonferansStreamSession.query.filter_by(room_id=ROOM_ID).delete()
    KonferansRecording.query.filter_by(room_id=ROOM_ID).delete()
    KonferansRoom.query.filter_by(room_id=ROOM_ID).delete()
    User.query.filter(User.whatsapp.in_([OWNER_WA, GUEST_WA])).delete(synchronize_session=False)
    db.session.commit()

    owner = User(name='Smoke Owner', pseudo='SmokeOwnerStream', whatsapp=OWNER_WA, password_hash='x', is_admin=False)
    guest = User(name='Smoke Guest', pseudo='SmokeGuestStream', whatsapp=GUEST_WA, password_hash='x')
    db.session.add_all([owner, guest])
    db.session.commit()

    room = KonferansRoom(room_id=ROOM_ID, room_code='SMOKSTR', room_name='Smoke Stream Room',
                         creator_name='Smoke Owner', user_id=owner.id, is_active=True)
    db.session.add(room)
    db.session.commit()
    owner_id, guest_id = owner.id, guest.id


def login(client, uid):
    with client.session_transaction() as s:
        s['_user_id'] = str(uid)
        s['_fresh'] = True


client = app.test_client()

# 1. Guest cannot start a stream
login(client, guest_id)
r = client.post(f'/konferans/api/stream/start/{ROOM_ID}', json={'platform': 'youtube', 'ingest_url': 'rtmp://a.rtmp.youtube.com/live2', 'stream_key': 'abcd-1234'})
check('guest start stream -> 403', r.status_code == 403)

# 2. Owner starts YouTube session
login(client, owner_id)
r = client.post(f'/konferans/api/stream/start/{ROOM_ID}', json={'platform': 'youtube', 'ingest_url': 'rtmp://a.rtmp.youtube.com/live2', 'stream_key': 'abcd-1234', 'title': 'Smoke Live'})
check('owner start stream -> 200', r.status_code == 200)
j = r.get_json()
check('start response success', j.get('success') is True)
check('stream key masked in response', j.get('session', {}).get('stream_key_masked', '').endswith('1234'))

# 3. Status endpoint (public) shows streaming
r = client.get(f'/konferans/api/stream/status/{ROOM_ID}')
j = r.get_json()
check('status shows streaming', j.get('streaming') is True and j.get('session', {}).get('platform') == 'youtube')

# 4. Duplicate start rejected
r = client.post(f'/konferans/api/stream/start/{ROOM_ID}', json={'platform': 'facebook', 'ingest_url': 'rtmps://live-api-s.facebook.com:443/rtmp/', 'stream_key': 'wxyz-9999'})
check('duplicate start -> 409', r.status_code == 409)

# 5. Validation: bad platform / bad ingest / short key
login(client, owner_id)
client.post(f'/konferans/api/stream/stop/{ROOM_ID}')
r = client.post(f'/konferans/api/stream/start/{ROOM_ID}', json={'platform': 'myspace', 'ingest_url': 'rtmp://x', 'stream_key': 'abcd1234'})
check('unknown platform -> 400', r.status_code == 400)
r = client.post(f'/konferans/api/stream/start/{ROOM_ID}', json={'platform': 'youtube', 'ingest_url': 'http://bad.example', 'stream_key': 'abcd1234'})
check('non-rtmp ingest -> 400', r.status_code == 400)
r = client.post(f'/konferans/api/stream/start/{ROOM_ID}', json={'platform': 'youtube', 'ingest_url': 'rtmp://a.rtmp.youtube.com/live2', 'stream_key': 'abc'})
check('short stream key -> 400', r.status_code == 400)

# 6. WhatsApp platform requires no ingest/key
r = client.post(f'/konferans/api/stream/start/{ROOM_ID}', json={'platform': 'whatsapp', 'title': 'Odio Save'})
check('whatsapp start -> 200', r.status_code == 200)
client.post(f'/konferans/api/stream/stop/{ROOM_ID}')

# 7. Platforms endpoint
r = client.get('/konferans/api/stream/platforms')
check('platforms endpoint lists 5 platforms', len(r.get_json().get('platforms', {})) == 5)

# 8. Stop + DB persistence
r = client.post(f'/konferans/api/stream/stop/{ROOM_ID}')
check('second stop -> 404 (nothing live)', r.status_code == 404)
with app.app_context():
    rows = KonferansStreamSession.query.filter_by(room_id=ROOM_ID).all()
    check('2 stream sessions persisted', len(rows) == 2)
    stopped = rows[-1]
    check('last session stopped with duration', stopped.status == 'stopped' and stopped.duration_seconds is not None)
    check('keys always masked', all((s.stream_key_masked or '').startswith('*') for s in rows if s.stream_key_masked))

# 9. Recording upload with title (WhatsApp save flow)
rec_blob = io.BytesIO(b'\x1a\x45\xdf\xa3fake-webm-data' * 10)
r = client.post(f'/konferans/upload_recording/{ROOM_ID}', data={
    'recording': (rec_blob, 'wa_audio_SMOKSTR.webm'),
    'title': 'Odio Konferans Smoke',
}, content_type='multipart/form-data')
check('upload recording -> 200', r.status_code == 200)
j = r.get_json()
check('title persisted', j.get('title') == 'Odio Konferans Smoke')
check('whatsapp_share_url present', 'wa.me' in (j.get('whatsapp_share_url') or ''))
with app.app_context():
    rec = KonferansRecording.query.filter_by(room_id=ROOM_ID).first()
    check('recording row title saved', rec is not None and rec.title == 'Odio Konferans Smoke')

# 10. Status after stop
r = client.get(f'/konferans/api/stream/status/{ROOM_ID}')
check('status not streaming after stop', r.get_json().get('streaming') is False)

# Cleanup
with app.app_context():
    rec = KonferansRecording.query.filter_by(room_id=ROOM_ID).first()
    if rec:
        try:
            os.remove(rec.file_path)
        except OSError:
            pass
    KonferansStreamSession.query.filter_by(room_id=ROOM_ID).delete()
    KonferansRecording.query.filter_by(room_id=ROOM_ID).delete()
    KonferansRoom.query.filter_by(room_id=ROOM_ID).delete()
    User.query.filter(User.whatsapp.in_([OWNER_WA, GUEST_WA])).delete(synchronize_session=False)
    db.session.commit()

print()
if fails:
    print(f'{len(fails)} FAILURES: {fails}')
    sys.exit(1)
print('ALL SMOKE TESTS PASSED')
