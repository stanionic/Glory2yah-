"""Phase 6 gateway half: offline voucher engine, WSGI portal, access control."""
import json
import os
import random
import sys
import threading
from io import BytesIO

import pytest

os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('SECRET_KEY', 'uwz-tests-secret')
os.environ.setdefault('WTF_CSRF_ENABLED', 'False')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p_ in (ROOT, os.path.join(ROOT, 'tests')):
    if p_ not in sys.path:
        sys.path.insert(0, p_)

import base64
from gateway_agent.portal import engine as E
from gateway_agent.portal.access import (AccessError, ArpMacResolver, NdsctlController,
                                         RecordingController)
from gateway_agent.portal.app import PortalApp
from gateway_agent.routers.base import ValidationFailed
from gateway_agent.store import Store

KEY = base64.b64encode(bytes(range(32))).decode()
T0 = 1_794_000_000
MAC1, MAC2, MAC3 = 'aa:bb:cc:00:00:01', 'aa:bb:cc:00:00:02', 'aa:bb:cc:00:00:03'
PKG = {'id': 1, 'name': '1 Hour', 'duration_minutes': 60, 'data_mb': None, 'down_kbps': 2000,
       'up_kbps': 1000, 'max_devices': 2, 'price_gkach': 50}
CODES = {'good': 'ABCD-EFGH-JKMN', 'second': 'PQRS-TUVW-XYZ2', 'revoked': 'ABCD-2345-6789',
         'expired': 'MMMM-NNNN-PPPP', 'single': 'SSSS-SSSS-SSSS'}


class Clock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t


def _iso(t):
    return E._iso(t)


def policy(vouchers=None, packages=None, can_sell=True, portal=None, key=KEY, name='Cyber Mapou'):
    vouchers = vouchers if vouchers is not None else [
        ('v_0000000001', CODES['good'], 'UNUSED', 1, T0 + 86400),
        ('v_0000000002', CODES['second'], 'UNUSED', 1, T0 + 86400),
        ('v_0000000003', CODES['revoked'], 'REVOKED', 1, T0 + 86400),
        ('v_0000000004', CODES['expired'], 'UNUSED', 1, T0 - 10),
        ('v_0000000005', CODES['single'], 'UNUSED', 2, T0 + 86400)]
    pk = packages or [PKG, dict(PKG, id=2, name='Solo', max_devices=1)]
    return {'voucher_key': key, 'vendor': {'uid': 'UWZ-X', 'name': name},
            'access': {'can_sell': can_sell, 'state': 'TRIAL' if can_sell else 'EXPIRED'},
            'portal': portal or {'brand_name': name, 'brand_color': '#0b6b3a', 'welcome_text': '',
                                 'voucher_enabled': True, 'free_access_enabled': False,
                                 'free_package_id': None, 'free_cooldown_hours': 24},
            'packages': pk,
            'vouchers': [{'uid': u, 'hash': E.hash_code(key, E.normalize_code(c)), 'package_id': p,
                          'status': s, 'expires_at': _iso(e)} for (u, c, s, p, e) in vouchers],
            'next_cursor': None}


@pytest.fixture()
def eng(tmp_path):
    clock = Clock()
    store = Store(str(tmp_path / 'gw.db'))
    e = E.VoucherEngine(store, clock)
    e.sync_from_cloud(policy())
    e.clock = clock
    return e


def events(e, type_=None):
    rows = e.store.db.execute('SELECT type,payload FROM events ORDER BY seq').fetchall()
    return [(t, json.loads(p)) for t, p in rows if type_ in (None, t)]


# ================================ engine ====================================
def test_agent_and_cloud_code_handling_are_identical():
    from app.wifi import voucher_service as vsv
    rnd = random.Random(7)
    samples = [''.join(rnd.choice(E.ALPHABET) for _ in range(12)) for _ in range(200)]
    noisy = ['abcd efgh jkmn', 'ABCD-EFGH-JKMN', ' abcdefghjkmn ', 'ABCD-EFGH-JKM', 'ABCD-EFGH-JKM0',
             'ABCD-EFGH-JKMNN', '', None, 'ABCD-EFGH-JKMI', 'ABCD-EFGH-JKMO', 'abcd-efgh-jkml']
    assert E.ALPHABET == vsv.ALPHABET and E.CODE_LEN == vsv.CODE_LEN
    for s in samples + noisy:
        assert E.normalize_code(s) == vsv.normalize_code(s), s
        n = E.normalize_code(s)
        if n:
            assert E.hash_code(KEY, n) == vsv.hash_code(KEY, n)


def test_redeem_grants_package_and_queues_one_cloud_event(eng):
    r = eng.redeem(CODES['good'], MAC1)
    assert r.ok and r.reason == 'ok'
    g = r.grant
    assert (g['package'], g['duration_s'], g['down_kbps'], g['up_kbps'], g['max_devices']) == (
        '1 Hour', 3600, 2000, 1000, 2)
    assert g['seconds_remaining'] == 3600 and g['reconnect'] is False
    ev = events(eng, 'voucher.redeemed')
    assert len(ev) == 1 and ev[0][1] == {
        'voucher_uid': 'v_0000000001', 'device': MAC1,
        'redeemed_at': _iso(T0), 'ends_at': _iso(T0 + 3600)}


def test_code_formats_are_forgiving(eng):
    assert eng.redeem('abcd efgh jkmn', MAC1).ok
    assert eng.redeem(' ABCDEFGHJKMN ', MAC1).grant['reconnect'] is True


def test_same_device_reconnects_without_new_event_and_second_device_attaches(eng):
    eng.redeem(CODES['good'], MAC1)
    eng.clock.t += 600
    r = eng.redeem(CODES['good'], MAC1)
    assert r.ok and r.grant['reconnect'] and r.grant['seconds_remaining'] == 3000
    assert len(events(eng, 'voucher.redeemed')) == 1
    r2 = eng.redeem(CODES['good'], MAC2)
    assert r2.ok and r2.grant['reconnect'] is False and r2.grant['seconds_remaining'] == 3000
    assert len(events(eng, 'voucher.redeemed')) == 2                 # device attach is reported
    r3 = eng.redeem(CODES['good'], MAC3)
    assert not r3.ok and r3.reason == 'device_limit'
    assert eng.redeem(CODES['good'], MAC1).ok                        # existing devices unaffected


@pytest.mark.parametrize('code', [
    'ZZZZ-ZZZZ-ZZZZ', 'short', '', None, 'ABCD-EFGH-JKM0', CODES['revoked'], CODES['expired']])
def test_every_kind_of_bad_code_gets_the_same_answer(eng, code):
    r = eng.redeem(code, MAC1)
    assert (r.ok, r.reason, r.grant, r.retry_after) == (False, 'invalid', None, None)


def test_used_up_voucher_looks_like_an_unknown_one(eng):
    eng.redeem(CODES['good'], MAC1)
    eng.clock.t += 3601
    eng.expire_due()
    assert eng.redeem(CODES['good'], MAC1).reason == 'invalid'
    assert eng.redeem(CODES['good'], MAC2).reason == 'invalid'


def test_bad_device_and_not_ready(tmp_path):
    clock = Clock()
    fresh = E.VoucherEngine(Store(str(tmp_path / 'n.db')), clock)
    assert fresh.redeem(CODES['good'], MAC1).reason == 'not_ready'          # never synced
    fresh.sync_from_cloud(policy())
    for bad in ('', 'nope', 'aa:bb:cc:00:00', None, 'aa:bb:cc:00:00:01;x'):
        assert fresh.redeem(CODES['good'], bad).reason == 'bad_device'


def test_device_lockout_blocks_even_the_correct_code_then_lifts(eng):
    for _ in range(5):
        eng.redeem('ZZZZ-ZZZZ-ZZZZ', MAC1)
    r = eng.redeem(CODES['good'], MAC1)                       # correct code, locked device
    assert r.reason == 'locked' and r.retry_after == 300
    assert eng.redeem(CODES['good'], MAC2).ok                 # another device is not locked
    eng.clock.t += 301
    assert eng.redeem(CODES['second'], MAC1).ok


def test_lockout_does_not_reveal_whether_the_code_exists(eng):
    for _ in range(5):
        eng.redeem('ZZZZ-ZZZZ-ZZZZ', MAC1)
    a, b = eng.redeem(CODES['good'], MAC1), eng.redeem('QQQQ-QQQQ-QQQQ', MAC1)
    assert (a.reason, a.grant) == (b.reason, b.grant) == ('locked', None)


def test_success_clears_failure_counter(eng):
    for _ in range(4):
        eng.redeem('ZZZZ-ZZZZ-ZZZZ', MAC1)
    assert eng.redeem(CODES['good'], MAC1).ok
    for _ in range(4):
        eng.redeem('ZZZZ-ZZZZ-ZZZZ', MAC1)
    assert eng.redeem(CODES['second'], MAC1).ok               # 4+4 is not 5 in a row


def test_global_limit_stops_mac_rotation_attacks(eng):
    for i in range(60):                                       # the documented global limit
        eng.redeem('ZZZZ-ZZZZ-ZZZZ', f'de:ad:be:ef:{i // 256:02x}:{i % 256:02x}')
    r = eng.redeem(CODES['good'], 'fe:ed:fa:ce:00:01')        # brand-new MAC, correct code
    assert r.reason == 'locked' and r.retry_after == E.GLOBAL_LOCK
    eng.clock.t += E.GLOBAL_LOCK + 2
    assert eng.redeem(CODES['good'], 'fe:ed:fa:ce:00:01').ok


def test_service_policy_stops_new_activations_but_protects_existing_customers(eng):
    eng.redeem(CODES['good'], MAC1)
    eng.sync_from_cloud(policy(can_sell=False))               # subscription ended
    r = eng.redeem(CODES['second'], MAC1)
    assert (r.ok, r.reason) == (False, 'unavailable')
    row = eng.store.db.execute("SELECT status FROM vouchers WHERE uid='v_0000000002'").fetchone()
    assert row[0] == 'unused'                                 # not consumed
    assert eng.store.db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0] == 0   # not a "failure"
    assert eng.redeem(CODES['good'], MAC1).grant['reconnect'] is True      # prepaid customer keeps access
    assert eng.redeem(CODES['good'], MAC2).ok                              # and their 2nd device


def test_a_voucher_is_spent_exactly_once_under_concurrency(eng):
    results = []

    def go(i):
        results.append(eng.redeem(CODES['single'], f'aa:00:00:00:00:{i:02x}'))
    ts = [threading.Thread(target=go, args=(i,)) for i in range(25)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sum(r.ok for r in results) == 1 and sum(r.reason == 'device_limit' for r in results) == 24
    assert len([e for e in events(eng, 'voucher.redeemed') if e[1]['voucher_uid'] == 'v_0000000005']) == 1


def test_device_cap_holds_under_concurrency_with_two_engines_on_one_db(tmp_path):
    """Two connections (as if two processes) hammer one SQLite file. EVERY request
    must complete without error, and the device cap must hold exactly."""
    path = str(tmp_path / 'shared.db')
    clock = Clock()
    e1, e2 = E.VoucherEngine(Store(path), clock), E.VoucherEngine(Store(path), clock)
    e1.sync_from_cloud(policy())
    out, errors, engines = [], [], (e1, e2)
    barrier = threading.Barrier(20)

    def go(i):
        try:
            barrier.wait()                                   # maximise contention
            out.append(engines[i % 2].redeem(CODES['good'], f'aa:11:00:00:00:{i:02x}'))
        except Exception as exc:                             # noqa: BLE001 - we want to see ANY failure
            errors.append(repr(exc))
    ts = [threading.Thread(target=go, args=(i,)) for i in range(20)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert errors == [], errors[:3]                          # no "database is locked" crashes
    assert len(out) == 20
    assert sum(r.ok for r in out) == 2                       # max_devices of the package
    assert sum(r.reason == 'device_limit' for r in out) == 18
    assert e1.store.db.execute('SELECT COUNT(*) FROM ent_devices').fetchone()[0] == 2
    assert len([e for e in events(e1, 'voucher.redeemed')]) == 2


def test_failure_inside_a_redemption_rolls_everything_back(eng, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError('disk full')
    monkeypatch.setattr(eng.store, 'enqueue', boom)
    with pytest.raises(RuntimeError):
        eng.redeem(CODES['good'], MAC1)
    st = eng.store.db.execute("SELECT status FROM vouchers WHERE uid='v_0000000001'").fetchone()[0]
    assert st == 'unused' and eng.store.db.execute('SELECT COUNT(*) FROM entitlements').fetchone()[0] == 0
    monkeypatch.undo()
    assert eng.redeem(CODES['good'], MAC1).ok                   # the customer can simply retry


def test_expiry_returns_devices_once_and_reports_session_end(eng):
    eng.redeem(CODES['good'], MAC1)
    eng.redeem(CODES['good'], MAC2)
    assert eng.expire_due() == []
    eng.clock.t += 3601
    assert sorted(eng.expire_due()) == [MAC1, MAC2]
    assert eng.expire_due() == []
    end = events(eng, 'session.ended')
    assert len(end) == 1 and end[0][1]['reason'] == 'time_expired' and sorted(end[0][1]['devices']) == [MAC1, MAC2]
    assert eng.status(MAC1) is None


def test_status_and_active_devices_survive_a_restart(eng, tmp_path):
    eng.redeem(CODES['good'], MAC1)
    eng.clock.t += 100
    again = E.VoucherEngine(Store(str(tmp_path / 'gw.db')), eng.clock)
    assert again.status(MAC1)['seconds_remaining'] == 3500
    assert [d for d, _ in again.active_devices()] == [MAC1]
    assert again.status(MAC3) is None and again.status('garbage') is None


def test_resync_never_resurrects_or_unrevokes_vouchers(eng):
    eng.redeem(CODES['good'], MAC1)
    eng.sync_from_cloud(policy())                               # cloud still says UNUSED for it
    assert eng.redeem(CODES['good'], MAC2).ok                   # attaches to the SAME entitlement (max 2)
    assert eng.redeem(CODES['good'], MAC3).reason == 'device_limit'
    assert eng.store.db.execute('SELECT COUNT(*) FROM entitlements').fetchone()[0] == 1
    st = lambda u: eng.store.db.execute('SELECT status FROM vouchers WHERE uid=?', (u,)).fetchone()[0]
    assert st('v_0000000001') == 'redeemed'
    pol = policy()
    pol['vouchers'][1]['status'] = 'REVOKED'                    # revoked in the cloud later
    eng.sync_from_cloud(pol)
    assert st('v_0000000002') == 'revoked' and eng.redeem(CODES['second'], MAC2).reason == 'invalid'
    pol['vouchers'][1]['status'] = 'UNUSED'
    eng.sync_from_cloud(pol)
    assert st('v_0000000002') == 'revoked'                      # un-revoke is impossible


def test_package_changes_replace_the_list_but_keep_granted_entitlements(eng):
    eng.redeem(CODES['good'], MAC1)
    eng.sync_from_cloud(policy(packages=[dict(PKG, duration_minutes=5)]))
    assert [p['duration_minutes'] for p in eng.packages()] == [5]
    assert eng.status(MAC1)['seconds_remaining'] == 3600        # customer keeps what they bought


# ----------------------------- free access ----------------------------------
FREE = {'id': 9, 'name': 'Free 15m', 'duration_minutes': 15, 'data_mb': None, 'down_kbps': 500,
        'up_kbps': 500, 'max_devices': 1, 'price_gkach': 0}
FREE_PORTAL = {'brand_name': 'X', 'brand_color': '#112233', 'welcome_text': '', 'voucher_enabled': True,
               'free_access_enabled': True, 'free_package_id': 9, 'free_cooldown_hours': 2}


def test_free_access_disabled_by_default(eng):
    assert eng.free_access(MAC1).reason == 'disabled'


def test_free_access_grant_reconnect_and_cooldown(eng):
    eng.sync_from_cloud(policy(packages=[PKG, FREE], portal=FREE_PORTAL))
    r = eng.free_access(MAC1)
    assert r.ok and r.grant['source'] == 'free' and r.grant['seconds_remaining'] == 900
    assert events(eng, 'session.started')[0][1]['source'] == 'free'
    assert eng.free_access(MAC1).grant['reconnect'] is True            # still active: no new grant
    assert len(events(eng, 'session.started')) == 1
    eng.clock.t += 901
    eng.expire_due()
    c = eng.free_access(MAC1)
    assert (c.ok, c.reason) == (False, 'cooldown') and c.retry_after == 7200 - 901
    assert eng.free_access(MAC2).ok                                    # other devices independent
    eng.clock.t += 7200
    assert eng.free_access(MAC1).ok


def test_free_access_respects_service_state_and_never_hands_out_a_paid_package(eng):
    eng.sync_from_cloud(policy(packages=[PKG, FREE], portal=FREE_PORTAL, can_sell=False))
    assert eng.free_access(MAC1).reason == 'unavailable'
    eng.sync_from_cloud(policy(packages=[PKG, dict(FREE, price_gkach=10)], portal=FREE_PORTAL))
    assert eng.free_access(MAC1).reason == 'not_ready'


# ================================ access ====================================
def test_ndsctl_builds_safe_argv_and_validates_mac():
    calls = []

    class R:
        returncode = 0

    def run(argv, **kw):
        calls.append((argv, kw))
        return R()
    c = NdsctlController(run=run)
    c.authorize('AA:BB:CC:00:00:01', '192.168.1.5', {})
    c.deauthorize('aa-bb-cc-00-00-01')
    assert calls[0][0] == ['/usr/bin/ndsctl', 'auth', 'aa:bb:cc:00:00:01']
    assert calls[1][0] == ['/usr/bin/ndsctl', 'deauth', 'aa:bb:cc:00:00:01']
    assert all(k['shell'] is False and k['timeout'] == 5 for _, k in calls)
    for evil in ('aa:bb:cc:00:00:01; reboot', '$(id)', '', 'aa:bb:cc:00:00:01 -x'):
        with pytest.raises(ValidationFailed):
            c.authorize(evil, '1.1.1.1', {})
    assert len(calls) == 2                                           # nothing executed for bad input


def test_ndsctl_failures_become_access_errors():
    import subprocess

    class Bad:
        returncode = 3
    with pytest.raises(AccessError):
        NdsctlController(run=lambda *a, **k: Bad()).authorize(MAC1, '1.1.1.1', {})

    def timeout(*a, **k):
        raise subprocess.TimeoutExpired('ndsctl', 5)
    with pytest.raises(AccessError):
        NdsctlController(run=timeout).deauthorize(MAC1)
    with pytest.raises(AccessError):
        NdsctlController(run=lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError())).authorize(MAC1, '1.1.1.1', {})


def test_arp_resolver_parses_real_table_and_rejects_partial_matches(tmp_path):
    f = tmp_path / 'arp'
    f.write_text('IP address       HW type     Flags       HW address            Mask     Device\n'
                 '192.168.1.50     0x1         0x2         AA:BB:CC:00:00:50     *        br-lan\n'
                 '192.168.1.5      0x1         0x2         aa:bb:cc:00:00:05     *        br-lan\n'
                 '192.168.1.60     0x1         0x0         00:00:00:00:00:00     *        br-lan\n'
                 '192.168.1.61     0x1         0x2         00:00:00:00:00:00     *        br-lan\n')
    r = ArpMacResolver(str(f))
    assert r.resolve('192.168.1.5') == 'aa:bb:cc:00:00:05'
    assert r.resolve('192.168.1.50') == 'aa:bb:cc:00:00:50'
    assert r.resolve('192.168.1.6') is None and r.resolve('192.168.1.60') is None
    assert r.resolve('192.168.1.61') is None
    assert r.resolve('not an ip') is None and r.resolve(None) is None
    assert ArpMacResolver(str(tmp_path / 'missing')).resolve('192.168.1.5') is None


# ================================ portal ====================================
class StubResolver:
    def __init__(self, table):
        self.table = table

    def resolve(self, ip):
        return self.table.get(ip)


IP1, IP2 = '192.168.1.50', '192.168.1.51'


@pytest.fixture()
def portal(eng):
    access = RecordingController()
    app = PortalApp(eng, access, StubResolver({IP1: MAC1, IP2: MAC2}))
    app.eng, app.access = eng, access
    return app


def call(app, method='GET', path='/', body='', ip=IP1, extra=None, length=None):
    env = {'REQUEST_METHOD': method, 'PATH_INFO': path, 'REMOTE_ADDR': ip,
           'CONTENT_LENGTH': str(len(body) if length is None else length),
           'wsgi.input': BytesIO(body.encode())}
    env.update(extra or {})
    out = {}

    def sr(status, headers):
        out['status'], out['headers'] = int(status.split()[0]), dict(headers)
    data = b''.join(app(env, sr)).decode()
    return out['status'], out['headers'], data


def test_home_page_shows_brand_form_and_packages(portal):
    s, h, body = call(portal)
    assert s == 200 and 'Cyber Mapou' in body and 'name="code"' in body
    assert '1 Hour' in body and '50 Gkach' in body and 'Aksè gratis' not in body


def test_free_button_only_when_enabled(portal):
    portal.eng.sync_from_cloud(policy(packages=[PKG, FREE], portal=FREE_PORTAL))
    assert 'Aksè gratis' in call(portal)[2]
    s, _, body = call(portal, 'POST', '/free')
    assert s == 200 and portal.access.calls[-1][0] == 'authorize'


def test_vendor_controlled_text_cannot_inject_html_or_css(portal):
    evil = '<script>alert(1)</script>'
    pol = policy(packages=[dict(PKG, name='"><img src=x onerror=alert(1)>')],
                 portal={'brand_name': evil, 'brand_color': 'red;}</style><script>x</script>',
                         'welcome_text': '<b onmouseover=alert(1)>hi</b>', 'voucher_enabled': True,
                         'free_access_enabled': False, 'free_package_id': None, 'free_cooldown_hours': 24})
    portal.eng.sync_from_cloud(pol)
    s, h, body = call(portal)
    for raw in ('<script>', '<img src=x', '<b onmouseover', 'red;}'):
        assert raw not in body
    assert '&lt;script&gt;' in body and '#0b6b3a' in body              # escaped + safe default colour


def test_every_response_carries_security_headers_and_no_cookies(portal):
    for args in (('GET', '/'), ('GET', '/health'), ('POST', '/redeem', 'code=bad'), ('GET', '/nope')):
        s, h, _ = call(portal, *args)
        assert "default-src 'none'" in h['Content-Security-Policy'] and "form-action 'self'" in h['Content-Security-Policy']
        assert h['X-Frame-Options'] == 'DENY' and h['Cache-Control'] == 'no-store'
        assert h['X-Content-Type-Options'] == 'nosniff' and 'Set-Cookie' not in h


def test_redeem_authorises_the_device_found_from_the_connection_not_the_request(portal):
    spoof = ('code=' + CODES['good'] + '&mac=de:ad:be:ef:00:01&client_mac=de:ad:be:ef:00:02')
    s, h, body = call(portal, 'POST', '/redeem', spoof, extra={
        'HTTP_X_FORWARDED_FOR': '192.168.1.51', 'HTTP_X_REAL_IP': '192.168.1.51'})
    assert s == 200 and 'Ou konekte' in body
    verb, mac, ip, grant = portal.access.calls[-1]
    assert (verb, mac, ip) == ('authorize', MAC1, IP1) and grant['seconds_remaining'] == 3600
    assert portal.eng.store.db.execute('SELECT device FROM ent_devices').fetchall() == [(MAC1,)]


def test_unknown_device_is_refused_without_touching_the_engine(portal):
    s, _, body = call(portal, 'POST', '/redeem', 'code=' + CODES['good'], ip='10.9.9.9')
    assert s == 400 and portal.access.calls == []
    assert portal.eng.store.db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0] == 0
    assert portal.eng.store.db.execute("SELECT status FROM vouchers WHERE uid='v_0000000001'").fetchone()[0] == 'unused'


def test_bad_codes_get_one_generic_answer_then_a_timed_lockout(portal):
    bodies = set()
    for code in ('ZZZZ-ZZZZ-ZZZZ', CODES['revoked'], CODES['expired'], 'x'):
        s, _, b = call(portal, 'POST', '/redeem', 'code=' + code)
        assert s == 400
        bodies.add(b)
    assert len(bodies) == 1
    call(portal, 'POST', '/redeem', 'code=ZZZZ-ZZZZ-ZZZZ')
    s, h, b = call(portal, 'POST', '/redeem', 'code=' + CODES['good'])
    assert s == 429 and h['Retry-After'] == '300' and 'Tann 5 minit' in b
    assert portal.access.calls == []


def test_access_failure_keeps_the_code_usable_for_a_retry(portal):
    class Flaky(RecordingController):
        fail = True

        def authorize(self, mac, ip, grant):
            if self.fail:
                raise AccessError('firewall busy')
            super().authorize(mac, ip, grant)
    portal.access = Flaky()
    s, _, b = call(portal, 'POST', '/redeem', 'code=' + CODES['good'])
    assert s == 503 and 'Antre kòd la ankò' in b
    portal.access.fail = False
    s, _, b = call(portal, 'POST', '/redeem', 'code=' + CODES['good'])        # reconnect path
    assert s == 200 and portal.access.calls[-1][1] == MAC1
    assert len(events(portal.eng, 'voucher.redeemed')) == 1


def test_device_limit_is_a_409(portal):
    portal.eng.sync_from_cloud(policy())
    call(portal, 'POST', '/redeem', 'code=' + CODES['single'])
    s, _, b = call(portal, 'POST', '/redeem', 'code=' + CODES['single'], ip=IP2)
    assert s == 409 and 'limit' in b


def test_status_endpoint_reports_remaining_time(portal):
    assert json.loads(call(portal, 'GET', '/status')[2]) == {
        'active': False, 'seconds_remaining': 0, 'package': None, 'data_mb': None}
    call(portal, 'POST', '/redeem', 'code=' + CODES['good'])
    portal.eng.clock.t += 60
    st = json.loads(call(portal, 'GET', '/status')[2])
    assert st['active'] and st['seconds_remaining'] == 3540 and st['package'] == '1 Hour'


def test_request_hygiene(portal):
    assert call(portal, 'POST', '/redeem', 'code=' + 'A' * 5000)[0] == 413
    assert call(portal, 'POST', '/redeem', 'x', length=-5)[0] == 413
    assert call(portal, 'POST', '/redeem', 'x', length=99999)[0] == 413
    s, h, _ = call(portal, 'GET', '/redeem')
    assert s == 405 and h['Allow'] == 'POST'
    assert call(portal, 'POST', '/status')[0] == 405
    assert call(portal, 'GET', '/admin')[0] == 404
    assert json.loads(call(portal, 'GET', '/health')[2]) == {'ok': True}


def test_internal_errors_never_leak_details(portal, monkeypatch):
    monkeypatch.setattr(portal.eng, 'redeem', lambda *a: (_ for _ in ()).throw(RuntimeError('secret-path /etc/x')))
    s, _, body = call(portal, 'POST', '/redeem', 'code=' + CODES['good'])
    assert s == 500 and 'secret-path' not in body and 'Traceback' not in body
