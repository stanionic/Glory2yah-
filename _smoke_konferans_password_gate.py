"""
Smoke/validation test: Konferans room password gate (direct-link bypass fix).

Covers:
  P-1  GET /konferans/room/<code> for a password-protected room renders the
       password page (konferans/room_password.html) for anonymous users
  P-2  hidden user_name + csrf fields are present, user_name preserved
  P-3  POST wrong password -> 403 with the error message, still gated
  P-4  POST correct password -> room page rendered, session flag set
  P-5  GET after success -> room page directly (no gate)
  P-6  Owner bypass: owner account gets the room page with no password
  P-7  Authenticated non-owner still sees the gate
  P-8  Room without password -> direct access (regression)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models import User, KonferansRoom

app = create_app()
app.config['WTF_CSRF_ENABLED'] = False
app.config['TESTING'] = True

OWNER_WA = '+50990000021'
GUEST_WA = '+50990000022'
ROOM_ID = 'SMOKE_PW_ROOM_1'
ROOM_CODE = 'SMOKPW1'
NOPW_ROOM_ID = 'SMOKE_PW_ROOM_2'
NOPW_ROOM_CODE = 'SMOKPW2'
ROOM_PASSWORD = 'sekou123'

fails = []


def check(name, cond):
    print(('  [OK]  ' if cond else '  [FAIL] ') + name)
    if not cond:
        fails.append(name)


# ---------- Runtime setup ----------
with app.app_context():
    db.create_all()
    KonferansRoom.query.filter(KonferansRoom.room_id.in_([ROOM_ID, NOPW_ROOM_ID])).delete()
    User.query.filter(User.whatsapp.in_([OWNER_WA, GUEST_WA])).delete(synchronize_session=False)
    db.session.commit()

    owner = User(name='Pw Owner', pseudo='PwOwner', whatsapp=OWNER_WA, password_hash='x')
    guest = User(name='Pw Guest', pseudo='PwGuest', whatsapp=GUEST_WA, password_hash='x')
    db.session.add_all([owner, guest])
    db.session.commit()

    db.session.add(KonferansRoom(
        room_id=ROOM_ID, room_code=ROOM_CODE, room_name='Pwoteje Room',
        creator_name='Pw Owner', user_id=owner.id, is_active=True,
        password=generate_password_hash(ROOM_PASSWORD)))
    db.session.add(KonferansRoom(
        room_id=NOPW_ROOM_ID, room_code=NOPW_ROOM_CODE, room_name='Open Room',
        creator_name='Pw Owner', user_id=owner.id, is_active=True))
    db.session.commit()
    owner_id, guest_id = owner.id, guest.id


def login(client, uid):
    with client.session_transaction() as s:
        s['_user_id'] = str(uid)
        s['_fresh'] = True


ROOM_MARKER = 'id="videoContainer"'

# ---------- P-1/P-2: anonymous direct link gets the gate page ----------
client = app.test_client()
r = client.get(f'/konferans/room/{ROOM_CODE}')
html = r.get_data(as_text=True)
check('P-1 gate page -> 200 (template renders)', r.status_code == 200)
check('P-1 gate page is the password form',
      'name="password"' in html and 'Sal Pwoteje' in html)
check('P-1 room page NOT served', ROOM_MARKER not in html)
check('P-2 hidden user_name field present', 'name="user_name"' in html)
check('P-2 csrf hidden field present', 'name="csrf_token"' in html)

r = client.get(f'/konferans/room/{ROOM_CODE}?user_name=Ti+Malis')
html2 = r.get_data(as_text=True)
check('P-2 user_name preserved in form', 'value="Ti Malis"' in html2)

# ---------- P-3: wrong password ----------
r = client.post(f'/konferans/room/{ROOM_CODE}',
                data={'password': 'movemodepas', 'user_name': 'Ti Malis'})
html3 = r.get_data(as_text=True)
check('P-3 wrong password -> 403', r.status_code == 403)
check('P-3 error message shown', 'Modpas sa pa kòrèk.' in html3)
check('P-3 still gated (room not served)', ROOM_MARKER not in html3)

# ---------- P-4: correct password ----------
r = client.post(f'/konferans/room/{ROOM_CODE}',
                data={'password': ROOM_PASSWORD, 'user_name': 'Ti Malis'})
html4 = r.get_data(as_text=True)
check('P-4 correct password -> 200 room page',
      r.status_code == 200 and ROOM_MARKER in html4)
check('P-4 password form gone', 'name="password"' not in html4)

# ---------- P-5: subsequent GET passes directly ----------
r = client.get(f'/konferans/room/{ROOM_CODE}')
check('P-5 GET after auth -> room page',
      r.status_code == 200 and ROOM_MARKER in r.get_data(as_text=True))

# ---------- P-6: owner bypass ----------
owner_client = app.test_client()
login(owner_client, owner_id)
r = owner_client.get(f'/konferans/room/{ROOM_CODE}')
check('P-6 owner bypass -> room page',
      r.status_code == 200 and ROOM_MARKER in r.get_data(as_text=True))

# ---------- P-7: authenticated non-owner still gated ----------
guest_client = app.test_client()
login(guest_client, guest_id)
r = guest_client.get(f'/konferans/room/{ROOM_CODE}')
html7 = r.get_data(as_text=True)
check('P-7 non-owner still gated',
      r.status_code == 200 and 'name="password"' in html7 and ROOM_MARKER not in html7)

# ---------- P-8: room without password -> direct access ----------
anon2 = app.test_client()
r = anon2.get(f'/konferans/room/{NOPW_ROOM_CODE}')
check('P-8 no-password room -> direct room page',
      r.status_code == 200 and ROOM_MARKER in r.get_data(as_text=True))

# ---------- Cleanup ----------
with app.app_context():
    KonferansRoom.query.filter(KonferansRoom.room_id.in_([ROOM_ID, NOPW_ROOM_ID])).delete()
    User.query.filter(User.whatsapp.in_([OWNER_WA, GUEST_WA])).delete(synchronize_session=False)
    db.session.commit()

print()
if fails:
    print(f'{len(fails)} FAILURES: {fails}')
    sys.exit(1)
print('ALL PASSWORD GATE TESTS PASSED')
