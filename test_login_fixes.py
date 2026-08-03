"""Verify all login system fixes - uses single module-level app instance"""
import os
import re
import sys

os.environ['FLASK_ENV'] = 'development'
# Disable Flask-Limiter IP-based limits for tests. Must be set BEFORE import.
os.environ['RATELIMIT_ENABLED'] = '0'

# Use the ALREADY-CREATED module-level app from app/__init__.py
# (do NOT call create_app() again - two instances share db/cache and conflict)
import app as app_module
from app import db, cache
from app.models.user import User
from app.routes.auth import _find_user_by_identifier, _cache_identifier_rate_limit

# The module-level app is created at import: app_module.app
flask_app = app_module.app
flask_app.config['RATELIMIT_ENABLED'] = False
flask_app.config['WTF_CSRF_ENABLED'] = False  # direct API-style testing

PASS = 0
FAIL = 0

def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")

with flask_app.app_context():
    print("=" * 60)
    print("LOGIN FIX VERIFICATION")
    print("=" * 60)

    # ── TEST 1: _find_user_by_identifier still works ──
    print("\n--- TEST 1: User identifier lookup ---")
    for ident, expected in [
        ('Admin509', 'Admin509'),
        ('admin509', 'Admin509'),
        ('+50942882076', 'Admin509'),
        ('50942882076', 'Admin509'),
        ('StanD', 'StanD'),
        ('stand', 'StanD'),
        ('testuser', 'testuser'),
    ]:
        u = _find_user_by_identifier(ident)
        check(f"lookup {ident!r}", u is not None and u.pseudo == expected, f"got {u.pseudo if u else None}")

    # ── TEST 2: _cache_identifier_rate_limit direct unit test ──
    print("\n--- TEST 2: Rate-limit function (unit test) ---")
    uid = "unit_test_identifier_123"
    try:
        if cache:
            cache.delete(f"rl:login_fail_id:{uid}")
    except Exception:
        pass
    results = []
    for i in range(7):
        blocked = _cache_identifier_rate_limit("login_fail_id", uid, 5, 300)
        results.append(blocked)
    check("6th attempt blocked (5 already recorded)", len(results) > 5 and results[5] is True, f"got {results}")
    check("7th attempt still blocked", len(results) > 6 and results[6] is True, f"got {results}")

    # ── TEST 3: Login success works (Admin509) - CSRF disabled ──
    print("\n--- TEST 3: Login success (Admin509) ---")
    client = flask_app.test_client()
    resp = client.post('/auth/login', data={
        'identifier': 'Admin509',
        'password': 'StanGlory2YahPub1986', 'remember': 'on'
    }, follow_redirects=False)
    check("login status 302", resp.status_code == 302, f"got {resp.status_code} loc={resp.headers.get('Location')}")
    with client.session_transaction() as sess:
        check("session _user_id set", sess.get('_user_id') == '1', f"got {sess.get('_user_id')}")

    # ── TEST 4: Successful logins do NOT count toward rate limit ──
    print("\n--- TEST 4: Successful logins do NOT count toward rate limit ---")
    blocked_seen = False
    for i in range(6):
        c = flask_app.test_client()
        resp = c.post('/auth/login', data={
            'identifier': 'Admin509',
            'password': 'StanGlory2YahPub1986', 'remember': 'on'
        }, follow_redirects=False)
        if resp.status_code != 302:
            blocked_seen = True
            print(f"    iteration {i}: status={resp.status_code}")
    check("6x successful login all 302 (NOT blocked)", not blocked_seen, "saw non-302")

    # ── TEST 5: 5+ failures trigger rate limit (end-to-end) ──
    print("\n--- TEST 5: 5+ failures trigger rate limit (end-to-end) ---")
    uid_e2e = "e2e_non_exist_user_xyz"
    try:
        if cache:
            cache.delete(f"rl:login_fail_id:{uid_e2e}")
    except Exception:
        pass
    blocked = False
    for i in range(8):
        c = flask_app.test_client()
        resp = c.post('/auth/login', data={
            'identifier': uid_e2e,
            'password': 'wrongpass', 'remember': 'on'
        }, follow_redirects=False)
        loc = resp.headers.get('Location', '')
        # On block, route returns redirect back to login with flash "5 esè..."
        if 'login' in loc:
            body = c.get(loc).data.decode()
            if '5 esè' in body:
                blocked = True
                break
    check("5x failures -> rate limit triggers", blocked, "never saw block message")

    # ── TEST 6: Successful login CLEARS the failure counter ──
    print("\n--- TEST 6: Successful login clears failure counter ---")
    try:
        if cache:
            cache.delete("rl:login_fail_id:testuser")
    except Exception:
        pass
    # Fail 3 times (each with fresh client)
    for i in range(3):
        c = flask_app.test_client()
        c.post('/auth/login', data={
            'identifier': 'testuser', 'password': 'WRONG', 'remember': 'on'
        }, follow_redirects=False)
    # Now login successfully
    c = flask_app.test_client()
    resp = c.post('/auth/login', data={
        'identifier': 'testuser', 'password': '123456', 'remember': 'on'
    }, follow_redirects=False)
    check("login after 3 fails works (302)", resp.status_code == 302, f"got {resp.status_code}")
    with c.session_transaction() as sess:
        check("logged in as testuser", sess.get('_user_id') == '2', f"got {sess.get('_user_id')}")
    # Counter should be cleared
    remaining = None
    try:
        if cache:
            remaining = cache.get("rl:login_fail_id:testuser")
    except Exception:
        pass
    check("failure counter cleared from cache", remaining is None or remaining == [], f"got {remaining}")

    # ── TEST 7: Register rejects invalid whatsapp ──
    print("\n--- TEST 7: Registration validates whatsapp/pseudo ---")
    c = flask_app.test_client()
    resp = c.post('/auth/register', data={
        'whatsapp': 'ABC',
        'pseudo': 'baduser1',
        'name': 'Bad',
        'password': 'pass1234',
    }, follow_redirects=False)
    loc = resp.headers.get('Location', '')
    body = c.get(loc).data.decode() if loc else ''
    check("invalid whatsapp -> redirects to register", 'register' in loc, f"loc={loc}")
    check("error message shown", 'kout' in body or 'WhatsApp' in body or 'Nimewo' in body, "no error text")
    bad = User.query.filter_by(pseudo='baduser1').first()
    check("no bad user created", bad is None, "user was created!")

    # ── TEST 8: Register accepts valid data ──
    print("\n--- TEST 8: Registration with valid data works ---")
    import uuid
    test_pseudo = f"fixuser_{uuid.uuid4().hex[:6]}"
    c = flask_app.test_client()
    resp = c.post('/auth/register', data={
        'whatsapp': '+50955554444',
        'pseudo': test_pseudo,
        'name': 'Test Fixture',
        'password': 'pass123',
    }, follow_redirects=False)
    check("valid registration succeeds", resp.status_code in (302, 303), f"got {resp.status_code} loc={resp.headers.get('Location')}")
    u = User.query.filter_by(pseudo=test_pseudo).first()
    check("user created", u is not None, f"not found (pseudo={test_pseudo})")
    if u:
        check("whatsapp stored clean", u.whatsapp == '+50955554444', f"got {u.whatsapp!r}")
        db.session.delete(u)
        db.session.commit()

    # ── TEST 9: Wrong password error flow (redirects back with identifier) ──
    print("\n--- TEST 9: Wrong password error flow ---")
    c = flask_app.test_client()
    resp = c.post('/auth/login', data={
        'identifier': 'StanD', 'password': 'WRONGPASS', 'remember': 'on'
    }, follow_redirects=False)
    loc = resp.headers.get('Location', '')
    check("wrong pw -> redirect (302/303)", resp.status_code in (302, 303), f"got {resp.status_code}")
    check("redirect back to login with last_identifier", 'login' in loc, f"loc={loc}")
    body = c.get(loc).data.decode() if loc else ''
    check("identifier preserved", 'StanD' in body, "identifier lost")

    # ── TEST 10: Login page hint updated ──
    print("\n--- TEST 10: Login page hint ---")
    c = flask_app.test_client()
    body = c.get('/auth/login').data.decode()
    check("hint shows StanD -> pass123", 'StanD' in body and 'pass123' in body, "hint missing")

    print("\n" + "=" * 60)
    print(f"RESULTS: {PASS} passed, {FAIL} failed")
    print("=" * 60)
    sys.exit(0 if FAIL == 0 else 1)