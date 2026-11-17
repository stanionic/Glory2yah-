"""Register/login regression + security tests for Glory2YahPub.

Run alone or with the suite. The IP-level flask-limiter is disabled here so the
per-account lockout logic can be tested in isolation.
"""
import os
import sys
import uuid

import pytest

os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('SECRET_KEY', 'auth-tests-secret')
os.environ.setdefault('WTF_CSRF_ENABLED', 'False')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import create_app, db, limiter
from app.models.user import User
from app.models.user_gkach import UserGkach

PW = 'Str0ng-Passw0rd!'


@pytest.fixture()
def app():
    a = create_app('testing')
    a.config['WTF_CSRF_ENABLED'] = False
    prev = limiter.enabled
    limiter.enabled = False
    yield a
    limiter.enabled = prev
    with a.app_context():
        db.session.remove()
        db.drop_all()


def _wa():
    return '+5094' + str(uuid.uuid4().int)[:7]


def _pseudo():
    return 'u' + uuid.uuid4().hex[:10]


def _register(c, whatsapp=None, pseudo=None, password=PW, **extra):
    data = {'whatsapp': _wa() if whatsapp is None else whatsapp,
            'pseudo': pseudo or _pseudo(),
            'name': 'Tester', 'password': password}
    data.update(extra)
    return c.post('/auth/register', data=data)


def _login(c, identifier, password, **extra):
    return c.post('/auth/login', data=dict({'identifier': identifier, 'password': password}, **extra))


def _logged_in(c):
    return c.get('/auth/profile').status_code == 200


# --------------------------------- register ---------------------------------
def test_register_happy_path_creates_active_user_wallet_and_session(app):
    c, wa, ps = app.test_client(), _wa(), _pseudo()
    r = _register(c, wa, ps)
    assert r.status_code == 302
    with app.app_context():
        u = User.query.filter_by(pseudo=ps).one()
        assert u.is_active and u.whatsapp == wa and u.password_hash != PW
        assert UserGkach.query.filter_by(user_id=u.id).count() == 1
    assert _logged_in(c)


@pytest.mark.parametrize('bad_pw', ['', 'abc', 'x' * 129])
def test_register_rejects_unacceptable_passwords(app, bad_pw):
    # NOTE: the product policy is deliberately lenient (>=4 chars or a 6-digit PIN);
    # this only locks in the floor/ceiling, it does not endorse the policy.
    c, ps = app.test_client(), _pseudo()
    _register(c, pseudo=ps, password=bad_pw)
    with app.app_context():
        assert User.query.filter_by(pseudo=ps).count() == 0


@pytest.mark.parametrize('bad_wa', ['+509', '+509ABC', 'abc', '', '+0000000000000000000000'])
def test_register_rejects_invalid_whatsapp(app, bad_wa):
    c, ps = app.test_client(), _pseudo()
    _register(c, whatsapp=bad_wa, pseudo=ps)
    with app.app_context():
        assert User.query.filter_by(pseudo=ps).count() == 0


def test_register_same_number_in_other_formats_is_a_duplicate(app):
    c, wa = app.test_client(), _wa()
    _register(c, wa, _pseudo())
    digits = wa.lstrip('+')
    for variant in (digits, f'{wa[:4]} {wa[4:]}', f'{wa[:4]}-{wa[4:]}'):
        _register(app.test_client(), variant, _pseudo())
    with app.app_context():
        assert User.query.filter_by(whatsapp=wa).count() == 1


def test_register_duplicate_pseudo_case_insensitive(app):
    ps = _pseudo()
    _register(app.test_client(), pseudo=ps)
    _register(app.test_client(), pseudo=ps.upper())
    with app.app_context():
        assert User.query.filter(db.func.lower(User.pseudo) == ps.lower()).count() == 1


def test_register_does_not_store_plaintext_or_leak_hash(app):
    c, ps = app.test_client(), _pseudo()
    _register(c, pseudo=ps)
    with app.app_context():
        u = User.query.filter_by(pseudo=ps).one()
        assert PW not in (u.password_hash or '') and u.password_hash.startswith(('pbkdf2', 'scrypt', 'argon'))
    assert PW.encode() not in c.get('/auth/profile').data


def test_register_when_logged_in_redirects(app):
    c = app.test_client()
    _register(c)
    r = c.get('/auth/register')
    assert r.status_code == 302


def test_register_rejects_html_in_pseudo(app):
    ps = '<script>alert(1)</script>'
    _register(app.test_client(), pseudo=ps)
    with app.app_context():
        assert User.query.filter_by(pseudo=ps).count() == 0


# ----------------------------------- login ----------------------------------
def _user(app, password=PW, active=True):
    wa, ps = _wa(), _pseudo()
    with app.app_context():
        u = User(whatsapp=wa, pseudo=ps, name='T', auth_provider='whatsapp', is_active=active)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
    return wa, ps


def test_login_by_pseudo_whatsapp_and_case_insensitive_pseudo(app):
    wa, ps = _user(app)
    for ident in (ps, wa, wa.lstrip('+'), ps.upper()):
        c = app.test_client()
        _login(c, ident, PW)
        assert _logged_in(c), ident


def test_login_wrong_password_and_unknown_user_look_identical(app):
    wa, ps = _user(app)
    c1, c2 = app.test_client(), app.test_client()
    r1 = _login(c1, ps, 'Wrong-Pass-1!')
    r2 = _login(c2, _pseudo(), 'Wrong-Pass-1!')
    assert not _logged_in(c1) and not _logged_in(c2)
    assert r1.status_code == r2.status_code
    b1 = app.test_client().get(r1.headers['Location']).data
    assert b'Wrong-Pass' not in b1


def test_deactivated_account_cannot_login(app):
    wa, ps = _user(app, active=False)
    c = app.test_client()
    _login(c, ps, PW)
    assert not _logged_in(c)


@pytest.mark.parametrize('evil', ['//evil.example', 'https://evil.example', '/\\evil.example',
                                  'javascript:alert(1)', '///evil.example', '\\\\evil.example'])
def test_login_next_is_not_an_open_redirect(app, evil):
    wa, ps = _user(app)
    c = app.test_client()
    r = _login(c, ps, PW, next=evil)
    loc = r.headers['Location']
    assert 'evil.example' not in loc and not loc.lower().startswith('javascript')


def test_login_next_local_path_is_honoured(app):
    wa, ps = _user(app)
    r = _login(app.test_client(), ps, PW, next='/auth/profile')
    assert r.headers['Location'].endswith('/auth/profile')


def test_logout_ends_session(app):
    wa, ps = _user(app)
    c = app.test_client()
    _login(c, ps, PW)
    assert _logged_in(c)
    c.get('/auth/logout')
    assert not _logged_in(c)


# ------------------------- brute-force lockout (BUG) -------------------------
def test_lockout_blocks_even_the_correct_password(app):
    """After 5 failures the account must be locked: a correct password is refused."""
    wa, ps = _user(app)
    c = app.test_client()
    for _ in range(5):
        _login(c, ps, 'Wrong-Pass-1!')
    assert not _logged_in(c)
    _login(c, ps, PW)                       # attacker finally guesses right
    assert not _logged_in(c), 'lockout did not block a correct password'


def test_lockout_counter_is_shared_across_identifier_spellings(app):
    wa, ps = _user(app)
    spellings = [ps, ps.upper(), wa, wa.lstrip('+'), f' {ps} ']
    for s in spellings:
        _login(app.test_client(), s, 'Wrong-Pass-1!')
    c = app.test_client()
    _login(c, ps, PW)
    assert not _logged_in(c), 'rotating the spelling reset the failure counter'


def test_lockout_is_per_account_not_global(app):
    wa1, ps1 = _user(app)
    wa2, ps2 = _user(app)
    for _ in range(5):
        _login(app.test_client(), ps1, 'Wrong-Pass-1!')
    c = app.test_client()
    _login(c, ps2, PW)
    assert _logged_in(c)


def test_successful_login_resets_failure_counter(app):
    wa, ps = _user(app)
    for _ in range(3):
        _login(app.test_client(), ps, 'Wrong-Pass-1!')
    c = app.test_client()
    _login(c, ps, PW)
    assert _logged_in(c)
    for _ in range(3):
        _login(app.test_client(), ps, 'Wrong-Pass-1!')
    c2 = app.test_client()
    _login(c2, ps, PW)
    assert _logged_in(c2)                    # 3+3 is not 5 in a row


# ------------------------------ password policy ------------------------------
from app.utils.validators import ValidationError, validate_password


@pytest.mark.parametrize('pw', [
    '482916', 'correct horse', 'Tr0ub4dor&3', 'ab1!ab1!', 'n0t-a-common-one',
])
def test_policy_accepts_good_passwords_and_non_trivial_pins(pw):
    assert validate_password(pw) is True


@pytest.mark.parametrize('pw', [
    '', 'abc', 'abcd', 'abcd1', '1234567', 'abcdefg',           # too short (non-PIN)
    '000000', '111111', '123456', '654321', '121212', '123123', '123321',   # trivial PINs
    'password', 'Password123', 'GLORY2YAH', '12345678', 'qwertyui',         # common
    'aaaaaaaa', 'x' * 129,
])
def test_policy_rejects_weak_passwords(pw):
    with pytest.raises(ValidationError):
        validate_password(pw)


def test_policy_rejects_password_equal_to_own_pseudo_or_number():
    with pytest.raises(ValidationError):
        validate_password('myusername', identifiers=('MyUserName',))
    with pytest.raises(ValidationError):
        validate_password('50937001234', identifiers=('+50937001234',))
    assert validate_password('myusername-2025', identifiers=('myusername',)) is True


@pytest.mark.parametrize('bad_pw', ['', 'abc', 'abcd1', '123456', 'password123', 'x' * 129])
def test_register_enforces_policy(app, bad_pw):
    c, ps = app.test_client(), _pseudo()
    _register(c, pseudo=ps, password=bad_pw)
    with app.app_context():
        assert User.query.filter_by(pseudo=ps).count() == 0


def test_register_rejects_password_equal_to_pseudo(app):
    ps = 'samename' + uuid.uuid4().hex[:4]
    _register(app.test_client(), pseudo=ps, password=ps)
    with app.app_context():
        assert User.query.filter_by(pseudo=ps).count() == 0


def test_existing_weak_passwords_can_still_log_in(app):
    """The new policy applies to NEW passwords only: nobody is locked out by it."""
    for legacy in ('abcd', '123456', 'pass'):
        wa, ps = _user(app, password=legacy)
        c = app.test_client()
        _login(c, ps, legacy)
        assert _logged_in(c), legacy


# ------------------------------ timed lockout message ------------------------
def _flashes(c, identifier_resp):
    return c.get(identifier_resp.headers['Location']).data.decode()


def test_lockout_message_says_how_long_to_wait(app):
    import re
    wa, ps = _user(app)
    c = app.test_client()
    for _ in range(5):
        _login(c, ps, 'Wrong-Pass-1!')
    r = _login(c, ps, PW)
    page = c.get(r.headers['Location']).data.decode()
    m = re.search(r'Tann (\d+) minit', page)
    assert m and 1 <= int(m.group(1)) <= 5, page[:400]
    assert 'lè Ayiti' in page                                  # clock time (tz data available)


def test_unknown_account_gets_the_identical_lock_message(app):
    """Locking must not reveal which accounts exist."""
    import re
    wa, ps = _user(app)
    ghost = _pseudo()
    pages = []
    for ident in (ps, ghost):
        c = app.test_client()
        for _ in range(5):
            _login(c, ident, 'Wrong-Pass-1!')
        r = _login(c, ident, 'Wrong-Pass-1!')
        pages.append(re.search(r'Twòp esè koneksyon invalide\. Tann \d+ minit[^<]*', c.get(
            r.headers['Location']).data.decode()))
    assert all(pages)
    norm = lambda m: re.sub(r'\d+', 'N', m.group(0))
    assert norm(pages[0]) == norm(pages[1])


def test_lock_expires_after_the_window(app):
    from app import cache
    wa, ps = _user(app)
    c = app.test_client()
    for _ in range(5):
        _login(c, ps, 'Wrong-Pass-1!')
    _login(c, ps, PW)
    assert not _logged_in(c)
    with app.app_context():
        uid = User.query.filter_by(pseudo=ps).one().id
        key = f'rl:login_fail_id:u{uid}'
        import time
        cache.set(key, [time.time() - 301] * 5, timeout=60)     # all failures now outside the window
    _login(c, ps, PW)
    assert _logged_in(c)


# ------------------------------ change password ------------------------------
def _cp(c, cur, new):
    return c.post('/auth/profile/change-password', data={'current_password': cur, 'new_password': new})


def test_change_password_does_not_strip_and_roundtrips(app):
    wa, ps = _user(app, password=' spaced pass1 ')              # legacy password with edge spaces
    c = app.test_client()
    _login(c, ps, ' spaced pass1 ')
    assert _logged_in(c)
    r = _cp(c, ' spaced pass1 ', ' new spaced 2 ')
    assert r.status_code == 200 and r.json['success'], r.json
    c2 = app.test_client()
    _login(c2, ps, ' new spaced 2 ')
    assert _logged_in(c2)                                       # exactly what was typed works
    c3 = app.test_client()
    _login(c3, ps, 'new spaced 2')
    assert not _logged_in(c3)


def test_change_password_enforces_policy_and_checks_current(app):
    wa, ps = _user(app)
    c = app.test_client()
    _login(c, ps, PW)
    assert _cp(c, 'wrong-current', 'An0ther-Good-One').status_code == 400
    assert _cp(c, PW, PW).status_code == 400                    # must differ
    for weak in ('abc', '123456', 'password123', ps):
        r = _cp(c, PW, weak)
        assert r.status_code == 400 and not r.json['success'], weak
    assert _cp(c, PW, 'An0ther-Good-One').json['success']
