"""Test admin user block/unblock functionality (uses module-level app + dev DB)."""
import os
import uuid

os.environ['FLASK_ENV'] = 'development'
os.environ['RATELIMIT_ENABLED'] = '0'

# Use the ALREADY-CREATED module-level app (do NOT call create_app() again)
import app as app_module
from app import db
from app.models.user import User

flask_app = app_module.app
flask_app.config['RATELIMIT_ENABLED'] = False
flask_app.config['WTF_CSRF_ENABLED'] = False

client = flask_app.test_client()

# Unique pseudos to avoid conflicts with existing dev data
suffix = uuid.uuid4().hex[:6]
ADMIN_PSEUDO = f"blkadmin_{suffix}"
U1_PSEUDO = f"blkuser1_{suffix}"
U2_PSEUDO = f"blkuser2_{suffix}"

with flask_app.app_context():
    admin = User(pseudo=ADMIN_PSEUDO, name='Block Test Admin', whatsapp=f'+5097{suffix}0001', is_admin=True, is_active=True)
    admin.set_password('adminpass')
    db.session.add(admin)
    u1 = User(pseudo=U1_PSEUDO, name='Block User 1', whatsapp=f'+5097{suffix}0002', is_active=True)
    u1.set_password('userpass')
    db.session.add(u1)
    u2 = User(pseudo=U2_PSEUDO, name='Block User 2', whatsapp=f'+5097{suffix}0003', is_active=True)
    u2.set_password('userpass2')
    db.session.add(u2)
    db.session.commit()
    ADMIN_ID, U1_ID, U2_ID = admin.id, u1.id, u2.id
    print(f"Users: admin={ADMIN_ID} u1={U1_ID} u2={U2_ID}")

def login(pseudo, pw):
    return client.post('/auth/login', data={'identifier': pseudo, 'password': pw}, follow_redirects=False)

try:
    # 1. Admin login
    r = login(ADMIN_PSEUDO, 'adminpass')
    assert r.status_code in (302, 303), f"Admin login failed: {r.status_code}"
    print("PASS: Admin login")

    # 2. Manage users page
    r = client.get('/admin/users')
    assert r.status_code == 200 and U1_PSEUDO in r.get_data(as_text=True) and 'Bloke' in r.get_data(as_text=True)
    print("PASS: Users page renders with Block buttons")

    # 3. Toggle block u1
    r = client.post(f'/admin/users/{U1_ID}/toggle', follow_redirects=True)
    with flask_app.app_context():
        assert User.query.get(U1_ID).is_active is False
    print("PASS: Toggle blocks user")

    # 4. Toggle unblock u1
    r = client.post(f'/admin/users/{U1_ID}/toggle', follow_redirects=True)
    with flask_app.app_context():
        assert User.query.get(U1_ID).is_active is True
    print("PASS: Toggle unblocks user")

    # 5. Block by pseudo (case-insensitive)
    r = client.post('/admin/users/block-by-pseudo', data={'pseudo': U2_PSEUDO.upper()}, follow_redirects=True)
    with flask_app.app_context():
        assert User.query.get(U2_ID).is_active is False
    print("PASS: Block by pseudo (case-insensitive)")

    # 6. Block already-blocked
    r = client.post('/admin/users/block-by-pseudo', data={'pseudo': U2_PSEUDO}, follow_redirects=True)
    assert 'deja bloke' in r.get_data(as_text=True)
    print("PASS: Already-blocked message")

    # 7. Non-existent pseudo
    r = client.post('/admin/users/block-by-pseudo', data={'pseudo': 'nobody'}, follow_redirects=True)
    assert 'pa jwenn' in r.get_data(as_text=True)
    print("PASS: Non-existent pseudo error")

    # 8. Admin cannot block self
    r = client.post(f'/admin/users/{ADMIN_ID}/toggle', follow_redirects=True)
    with flask_app.app_context():
        assert User.query.get(ADMIN_ID).is_active is True
    print("PASS: Admin cannot block self")

    # 9. Blocked user cannot login
    with flask_app.app_context():
        User.query.get(U2_ID).is_active = False
        db.session.commit()
    # Use a FRESH client (no admin session) so the login route processes the blocked user
    fresh_client = flask_app.test_client()
    r = fresh_client.post('/auth/login', data={'identifier': U2_PSEUDO, 'password': 'userpass2'}, follow_redirects=True)
    body = r.get_data(as_text=True).lower()
    assert 'dezaktive' in body, f"Blocked message not found. Body snippet: {body[:800]}"
    print("PASS: Blocked user cannot login")

    print("\nALL TESTS PASSED")
finally:
    # Clean up test users
    with flask_app.app_context():
        for uid in (ADMIN_ID, U1_ID, U2_ID):
            u = User.query.get(uid)
            if u:
                db.session.delete(u)
        db.session.commit()
        print("Cleanup: test users removed")