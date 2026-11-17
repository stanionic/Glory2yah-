"""Phase 8: trusted time, rollback detection, signed offline licenses, lapse behaviour."""
import base64
import json
import os
import sys
import time
import uuid
from datetime import timedelta

import pytest

os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('SECRET_KEY', 'uwz-tests-secret')
os.environ.setdefault('WTF_CSRF_ENABLED', 'False')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p_ in (ROOT, os.path.join(ROOT, 'tests')):
    if p_ not in sys.path:
        sys.path.insert(0, p_)

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app import create_app, db
from app.models.user import User
from app.services.gkach_service import GkachService
from app.wifi import vendor_service as vs
from app.wifi.models import WifiAuditLog, WifiGateway, WifiTrial, WifiVendor
from app.wifi.policy import set_policy
from gateway_agent.agent import GatewayAgent
from gateway_agent.license import LicenseManager
from gateway_agent.portal import engine as E
from gateway_agent.store import Store
from gateway_agent.timeguard import TrustedClock
from test_wifi_gateway import _login
from test_wifi_offline_e2e import IP1, IP2, IP3, MAC1, World
from test_wifi_portal import CODES, KEY, T0, call, policy

DAY = 86400


class Fake:
    """Controllable time sources (wall clock, monotonic clock, boot identity)."""
    def __init__(self, wall=float(T0), mono=1000.0, boot='boot-1'):
        self.wall, self.mono, self.boot = wall, mono, boot

    def advance(self, s):                 # normal passage of time
        self.wall += s
        self.mono += s

    def wall_fn(self): return self.wall
    def mono_fn(self): return self.mono
    def boot_fn(self): return self.boot


def mkclock(store, fake, **kw):
    return TrustedClock(store, wall=fake.wall_fn, mono=fake.mono_fn, boot_id=fake.boot_fn, **kw)


@pytest.fixture()
def store(tmp_path):
    return Store(str(tmp_path / 'c.db'))


# ================================= trusted clock ==============================
def test_trusted_time_ignores_wall_clock_changes_once_anchored(store):
    f = Fake()
    c = mkclock(store, f)
    c.sync_with_cloud(T0)
    f.advance(100)
    assert c.now() == T0 + 100
    f.wall -= 10 * DAY                                    # attacker sets the clock back
    assert c.now() == T0 + 100
    f.wall += 40 * DAY                                    # ...or far forward
    assert c.now() == T0 + 100
    f.mono += 50                                          # only REAL elapsed time moves trusted time
    assert c.now() == T0 + 150


def test_trusted_time_never_goes_backwards_within_a_boot(store):
    f = Fake()
    c = mkclock(store, f)
    c.sync_with_cloud(T0)
    last, rnd = c.now(), __import__('random').Random(3)
    for _ in range(200):
        f.wall += rnd.choice([-5 * DAY, -1, 0, 7, 3 * DAY])
        f.mono += rnd.choice([0, 1, 5])
        t = c.now()
        assert t >= last
        last = t


def test_rollback_detection_ignores_ntp_sized_steps_and_clears_on_cloud_sync(store):
    f = Fake()
    c = mkclock(store, f)
    c.sync_with_cloud(T0)
    assert c.observe() == []
    f.wall -= 60                                          # NTP-sized correction: not a rollback
    assert c.observe() == [] and not c.rollback_since_sync
    f.wall -= 3600
    found = c.observe()
    assert [(a['kind'], a['delta_s']) for a in found] == [('clock_rollback', 3660)]
    assert c.rollbacks == 1 and c.rollback_since_sync
    assert c.observe() == []                              # the same step is not re-flagged
    c.sync_with_cloud(T0 + 10)
    assert not c.rollback_since_sync and c.rollbacks == 1


def test_time_continues_from_the_high_water_mark_after_a_reboot(store):
    f = Fake()
    c = mkclock(store, f)
    c.sync_with_cloud(T0)
    f.advance(400)
    c.observe()                                           # persists (>= 300s of progress)
    f2 = Fake(wall=1000.0, mono=5.0, boot='boot-2')       # RTC-less router: wall clock reset to ~1970
    c2 = mkclock(store, f2)
    assert c2.now() == T0 + 400                           # not 1970, not frozen at a stale value
    f2.advance(60)
    assert c2.now() == T0 + 460                           # and it advances with real elapsed time


def test_setting_the_clock_back_before_a_reboot_neither_freezes_nor_rewinds_time(store):
    f = Fake()
    c = mkclock(store, f)
    c.sync_with_cloud(T0)
    f.advance(400)
    c.observe()
    f2 = Fake(wall=T0 - 10 * DAY, mono=7.0, boot='boot-2')    # attacker: 10 days back + power cycle
    c2 = mkclock(store, f2)
    assert c2.now() == T0 + 400
    f2.advance(3600)
    assert c2.now() == T0 + 4000                              # time keeps flowing: no "frozen licence"


def test_a_genuinely_later_wall_clock_after_reboot_is_used(store):
    f = Fake()
    c = mkclock(store, f)
    c.sync_with_cloud(T0)
    f.advance(400)
    c.observe()
    c2 = mkclock(store, Fake(wall=T0 + 10_000.0, mono=3.0, boot='boot-2'))
    assert c2.now() == T0 + 10_000


def test_signed_floor_is_a_hard_lower_bound_and_survives_reboot(store):
    f = Fake()
    c = mkclock(store, f)
    c.sync_with_cloud(T0)
    c.raise_floor(T0 + 1_000_000)
    assert c.now() == T0 + 1_000_000
    c2 = mkclock(store, Fake(wall=5.0, mono=1.0, boot='boot-9'))
    assert c2.now() >= T0 + 1_000_000


def test_persistence_is_throttled_to_protect_flash_storage(store):
    f = Fake()
    c = mkclock(store, f)
    c.sync_with_cloud(T0)
    writes = []
    real = store.set
    store.set = lambda k, v: (writes.append(k), real(k, v))[1]
    for _ in range(50):
        f.advance(1)
        c.observe()
    assert writes == []                                       # 50s of progress: no disk writes
    f.advance(300)
    c.observe()
    assert writes == ['clock']                                # one write once 300s have passed


def test_without_a_boot_id_a_process_restart_counts_as_a_reboot(store):
    f = Fake()
    f.boot = None
    c = mkclock(store, f)
    c.sync_with_cloud(T0)
    assert c.status()['anchored'] is True and c.status()['trusted_now'] == T0


# ================================== license ===================================
@pytest.fixture()
def lic(store):
    f = Fake()
    clock = mkclock(store, f)
    clock.sync_with_cloud(T0)
    key = Ed25519PrivateKey.generate()
    pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    store.set('cloud_public_key', base64.b64encode(pub).decode())
    store.set('gateway_uid', 'gw_test')
    store.set('vendor_uid', 'UWZ-TEST')
    mgr = LicenseManager(store, clock)

    def make(signer=None, **over):
        p = {'v': 1, 'k': 'license', 'lid': 'lc_' + '0' * 16, 'vendor': 'UWZ-TEST', 'gw': 'gw_test',
             'iat': T0, 'trial_exp': T0 + 3 * DAY, 'sub_exp': None, 'eff': T0 + 3 * DAY, 'grace': 3,
             'status': 'ACTIVE'}
        p.update(over)
        b = base64.urlsafe_b64encode(json.dumps(p, separators=(',', ':'), sort_keys=True).encode()
                                     ).rstrip(b'=').decode()
        sig = (signer or key).sign(b.encode())
        return b + '.' + base64.urlsafe_b64encode(sig).rstrip(b'=').decode()
    return type('L', (), {'mgr': mgr, 'clock': clock, 'fake': f, 'make': staticmethod(make), 'store': store,
                          'key': key})


def test_valid_license_installs_and_reports_time_left(lic):
    assert lic.mgr.install(lic.make()) == (True, 'ok')
    st = lic.mgr.state()
    assert st['state'] == 'ACTIVE' and st['can_sell'] and st['seconds_left'] == 3 * DAY
    assert st['grace_ends'] == T0 + 6 * DAY


@pytest.mark.parametrize('over,reason', [
    ({'gw': 'gw_other'}, 'wrong_binding'), ({'vendor': 'UWZ-OTHER'}, 'wrong_binding'),
    ({'grace': 31}, 'malformed'), ({'grace': -1}, 'malformed'), ({'status': 'ROOT'}, 'malformed'),
    ({'iat': True}, 'malformed'), ({'lid': 'nope'}, 'malformed'), ({'v': 2}, 'malformed'),
    ({'k': 'ticket'}, 'malformed'), ({'eff': 'tomorrow'}, 'malformed'),
])
def test_bad_licenses_are_rejected(lic, over, reason):
    assert lic.mgr.install(lic.make(**over)) == (False, reason)
    assert lic.mgr.state()['state'] == 'NONE'


def test_forged_tampered_and_garbage_licenses_are_rejected(lic):
    good = lic.make()
    forged = lic.make(signer=Ed25519PrivateKey.generate())
    body, sig = good.split('.')
    pad = lambda x: x + '=' * (-len(x) % 4)
    payload = json.loads(base64.urlsafe_b64decode(pad(body)))
    payload['eff'] = T0 + 10_000 * DAY
    tampered = base64.urlsafe_b64encode(json.dumps(payload, separators=(',', ':'), sort_keys=True).encode()
                                        ).rstrip(b'=').decode() + '.' + sig
    for bad in (forged, tampered, '', 'x', 'a.b', good + 'x', body, sig, None, 123, 'x' * 5000):
        assert lic.mgr.install(bad)[0] is False, str(bad)[:20]
    assert lic.mgr.state()['state'] == 'NONE'


def test_an_older_license_cannot_replace_a_newer_one(lic):
    assert lic.mgr.install(lic.make(iat=T0 + 100, eff=T0 + 100))[0]
    assert lic.mgr.install(lic.make(iat=T0, eff=T0 + 30 * DAY)) == (False, 'older_than_installed')
    assert lic.mgr.state()['effective_until'] == T0 + 100          # the replay did not extend anything
    assert lic.mgr.install(lic.make(iat=T0 + 100, eff=T0 + 100))[0]     # same issue time: idempotent
    assert lic.mgr.install(lic.make(iat=T0 + 200, eff=T0 + 9 * DAY))[0]
    assert lic.mgr.state()['effective_until'] == T0 + 9 * DAY


def test_installing_a_license_raises_the_trusted_time_floor(lic):
    lic.mgr.install(lic.make(iat=T0 + 500))
    assert lic.clock.now() == T0 + 500


def test_state_machine_active_grace_expired_uses_the_licenses_own_grace(lic):
    lic.mgr.install(lic.make())                                      # eff = T0+3d, grace 3d
    eff = T0 + 3 * DAY
    at = lambda t: (setattr(lic.fake, 'mono', 1000.0 + (t - T0)), lic.mgr.state())[1]
    assert at(eff - 1)['state'] == 'ACTIVE'
    assert (at(eff)['state'], at(eff)['can_sell']) == ('GRACE', True)
    assert at(eff + 3 * DAY - 1)['state'] == 'GRACE'
    s = at(eff + 3 * DAY)
    assert (s['state'], s['can_sell']) == ('EXPIRED', False) and 'renew' in s['reason']
    lic.mgr.install(lic.make(iat=T0 + 1, grace=0))                    # policy says: no grace
    assert at(eff)['state'] == 'EXPIRED'
    lic.mgr.install(lic.make(iat=T0 + 2, grace=7))
    assert at(eff + 6 * DAY)['state'] == 'GRACE' and at(eff + 7 * DAY)['state'] == 'EXPIRED'


def test_no_plan_suspended_and_untrusted_clock_block_new_sales(lic):
    assert lic.mgr.state()['state'] == 'NONE' and not lic.mgr.state()['can_sell']
    lic.mgr.install(lic.make(eff=None, trial_exp=None))
    assert lic.mgr.state()['state'] == 'EXPIRED' and 'no active plan' in lic.mgr.state()['reason']
    lic.mgr.install(lic.make(iat=T0 + 1, status='SUSPENDED'))
    assert (lic.mgr.state()['state'], lic.mgr.state()['can_sell']) == ('SUSPENDED', False)
    lic.mgr.install(lic.make(iat=T0 + 2))
    assert lic.mgr.state()['state'] == 'ACTIVE'
    lic.fake.wall -= 5 * DAY
    lic.clock.observe()
    s = lic.mgr.state()
    assert (s['state'], s['can_sell']) == ('UNTRUSTED_CLOCK', False) and 'cloud sync' in s['reason']
    lic.clock.sync_with_cloud(T0 + 5)
    assert lic.mgr.state()['state'] == 'ACTIVE'


# ============================ engine decisions (offline) ======================
LONG_LIVED = [('v_000000000%d' % i, c, 'UNUSED', 1, T0 + 60 * DAY)
              for i, c in enumerate([CODES['good'], CODES['second'], CODES['single']], start=1)]


@pytest.fixture()
def gw(lic):
    eng = E.VoucherEngine(lic.store, lic.clock.now)
    eng.license = lic.mgr
    eng.sync_from_cloud(policy(vouchers=LONG_LIVED))                  # cloud said: can_sell True
    lic.store.set('last_cloud_ok_epoch', int(lic.clock.now()))
    lic.mgr.install(lic.make())
    lic.eng = eng
    return lic


def _stale(g):
    g.fake.advance(1200)                                              # cloud last heard > 15 min ago


def test_offline_sales_follow_the_license_not_a_stale_cloud_answer(gw):
    assert gw.eng.can_sell() is True
    _stale(gw)
    assert gw.eng.can_sell() is True                                  # license ACTIVE
    gw.fake.advance(3 * DAY)                                          # into GRACE
    assert gw.eng.can_sell() is True
    assert gw.eng.redeem(CODES['good'], 'aa:bb:cc:00:00:01').ok       # sales still allowed in grace
    gw.fake.advance(3 * DAY)                                          # beyond grace
    assert gw.eng.can_sell() is False
    r = gw.eng.redeem(CODES['second'], 'aa:bb:cc:00:00:02')
    assert (r.ok, r.reason) == (False, 'unavailable')


def test_expired_license_protects_existing_customers_and_local_data(gw):
    assert gw.eng.redeem(CODES['good'], 'aa:bb:cc:00:00:01').ok
    _stale(gw)
    gw.fake.advance(6 * DAY - 1200 - 1800)                            # shortly before grace ends
    assert gw.eng.redeem(CODES['second'], 'aa:bb:cc:00:00:02').ok
    gw.fake.advance(1900)                                             # grace over by 100s; sale was 1900s ago (3600s package)
    assert gw.eng.can_sell() is False
    assert gw.eng.redeem(CODES['second'], 'aa:bb:cc:00:00:02').grant['reconnect'] is True   # session continues
    assert gw.eng.status('aa:bb:cc:00:00:02')['seconds_remaining'] > 0
    assert gw.eng.store.db.execute('SELECT COUNT(*) FROM vouchers').fetchone()[0] == 3      # history intact
    assert gw.eng.free_access('aa:bb:cc:00:00:03').reason in ('disabled', 'unavailable')


def test_fresh_cloud_answer_overrides_the_license_in_both_directions(gw):
    gw.fake.advance(7 * DAY)                                          # license long expired
    assert gw.mgr.state()['state'] == 'EXPIRED'
    gw.store.set('access', {'can_sell': True, 'state': 'SUBSCRIBED'})  # renewed on the cloud just now
    gw.store.set('last_cloud_ok_epoch', int(gw.clock.now()))
    assert gw.eng.can_sell() is True
    gw.store.set('access', {'can_sell': False, 'state': 'SUSPENDED'})  # suspended just now
    assert gw.eng.can_sell() is False


def test_clock_rollback_pauses_new_sales_only_until_the_next_cloud_sync(gw):
    assert gw.eng.redeem(CODES['good'], 'aa:bb:cc:00:00:01').ok
    gw.fake.wall -= 10 * DAY
    gw.clock.observe()
    assert gw.eng.can_sell() is False
    assert gw.eng.redeem(CODES['second'], 'aa:bb:cc:00:00:02').reason == 'unavailable'
    assert gw.eng.redeem(CODES['good'], 'aa:bb:cc:00:00:01').grant['reconnect'] is True
    gw.clock.sync_with_cloud(gw.clock.now())
    gw.store.set('last_cloud_ok_epoch', int(gw.clock.now()))
    assert gw.eng.can_sell() is True


def test_nothing_known_means_not_ready_and_legacy_cloud_only_mode_still_works(tmp_path):
    st = Store(str(tmp_path / 'n.db'))
    eng = E.VoucherEngine(st, lambda: float(T0))
    assert eng.can_sell() is None                                     # no license, no cloud answer
    eng.sync_from_cloud(policy(can_sell=False))
    assert eng.can_sell() is False                                    # legacy: cloud answer only
    eng.sync_from_cloud(policy(can_sell=True))
    assert eng.can_sell() is True


# =================================== cloud ====================================
@pytest.fixture()
def app():
    a = create_app('testing')
    a.config['WTF_CSRF_ENABLED'] = False
    yield a
    with a.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def world(app, tmp_path):
    w = World(app, tmp_path)
    assert w.agent.run_once()['authorized']
    return w


def _license_payload(world):
    tok = world.agent.store.get('license')['token']
    return world.agent.license._verify(tok)


def test_heartbeat_delivers_a_signed_license_with_the_right_terms(app, world):
    p = _license_payload(world)
    with app.app_context():
        trial_end = WifiTrial.query.filter_by(vendor_id=world.vid).one().expires_at
        vuid = db.session.get(WifiVendor, world.vid).vendor_uid
    assert set(p) == {'v', 'k', 'lid', 'vendor', 'gw', 'iat', 'trial_exp', 'sub_exp', 'eff', 'grace', 'status'}
    assert (p['vendor'], p['gw'], p['status'], p['grace'], p['sub_exp']) == (
        vuid, world.agent.store.get('gateway_uid'), 'ACTIVE', 3, None)
    assert p['eff'] == p['trial_exp'] == int(trial_end.replace(tzinfo=__import__('datetime').timezone.utc).timestamp())
    assert abs(p['iat'] - time.time()) < 10 and p['lid'].startswith('lc_')
    assert world.agent.status()['license']['state'] == 'ACTIVE'


def test_license_reflects_renewal_and_the_admin_grace_policy(app, world):
    before = _license_payload(world)['eff']
    with app.app_context():
        wa = db.session.get(WifiVendor, world.vid).user.whatsapp
        GkachService.add_balance(wa, 1000)
        set_policy('offline_grace_days', 5)
        db.session.commit()
    r = _login(app, world.uid).post('/wifi/vendor/subscription/renew', headers={'Idempotency-Key': 'renew-key-0001'})
    assert r.status_code == 201
    world.agent.run_once()
    p = _license_payload(world)
    assert p['eff'] > before + 29 * DAY and p['sub_exp'] == p['eff'] and p['grace'] == 5
    assert world.agent.status()['license']['grace_ends'] == p['eff'] + 5 * DAY


def test_suspended_vendors_get_a_suspended_license(app, world):
    with app.app_context():
        vs.suspend_vendor(db.session.get(WifiVendor, world.vid), 'abuse')
        db.session.commit()
    world.agent.run_once()
    st = world.agent.status()['license']
    assert (st['state'], st['can_sell']) == ('SUSPENDED', False)


def test_a_revoked_gateway_gets_no_new_license(app, world):
    old = world.agent.store.get('license')['lid']
    _login(app, world.uid).post(f'/wifi/vendor/gateways/{world.gid}/revoke')
    assert world.agent.run_once()['authorized'] is False
    assert world.agent.store.get('license')['lid'] == old


def test_heartbeat_survives_a_missing_signing_key(app, world, monkeypatch):
    monkeypatch.delenv('UWZ_LICENSE_SIGNING_KEY', raising=False)
    app.config['TESTING'] = False
    app.debug = False
    hb = world.agent.client.heartbeat()
    assert hb['license'] is None and hb['access']['can_sell'] is True


def test_gateway_clock_health_is_recorded_and_visible_to_admins(app, world):
    world.agent.run_once()
    with app.app_context():
        g = WifiGateway.query.one()
        assert isinstance(g.last_clock_skew_s, int) and abs(g.last_clock_skew_s) < 10 and g.clock_rollbacks == 0
    f = Fake(wall=time.time())
    clk = mkclock(world.agent.store, f)
    world.agent.clock, world.agent.engine.now_fn = clk, clk.now
    world.agent.license = world.agent.engine.license = LicenseManager(world.agent.store, clk)
    world.agent.run_once()
    f.wall -= 3600
    world.agent.maintain()                                         # detects the rollback offline
    world.agent.run_once()
    with app.app_context():
        g = WifiGateway.query.one()
        assert g.clock_rollbacks >= 1
        assert WifiAuditLog.query.filter_by(action='gateway.clock_rollback').count() == 1
        admin = User(whatsapp='+5094' + str(uuid.uuid4().int)[:7], pseudo='a' + uuid.uuid4().hex[:8], name='A',
                     is_active=True, is_admin=True)
        admin.set_password('Str0ng-Passw0rd!')
        db.session.add(admin)
        db.session.commit()
        aid = admin.id
    row = _login(app, aid).get('/wifi/admin/gateways').json['gateways'][0]
    assert row['clock_rollbacks'] >= 1 and row['license_state'] == 'OK'


@pytest.mark.parametrize('payload,logged', [
    ({'kind': 'clock_rollback', 'delta_s': 3600}, 1), ({'kind': 'clock_rollback', 'delta_s': -5}, 0),
    ({'kind': 'clock_rollback', 'delta_s': True}, 0), ({'kind': 'clock_rollback'}, 0),
    ({'kind': 'something_else'}, 0), ({}, 0)])
def test_gateway_events_are_audited_only_when_well_formed(app, world, payload, logged):
    world.agent.record_event('gateway.event', payload)
    assert world.agent.run_once()['pending'] == 0
    with app.app_context():
        assert WifiAuditLog.query.filter_by(action='gateway.clock_rollback').count() == logged


def test_vendor_is_notified_once_per_lapse_and_once_on_restore(app, world, monkeypatch):
    sent = []
    monkeypatch.setattr('app.wifi.subscription_service._notify',
                        lambda vendor, title, msg: sent.append(title)
                        if 'renouvel' not in title else None)           # ignore the renewal receipt itself
    world.agent.run_once()
    assert sent == []                                              # healthy: silence
    with app.app_context():
        set_policy('offline_grace_days', 0)
        WifiTrial.query.filter_by(vendor_id=world.vid).update({'expires_at': vs.utcnow() - timedelta(days=1)})
        db.session.commit()
    world.agent.run_once()
    world.agent.run_once()
    assert len(sent) == 1 and 'fini' in sent[0]                    # exactly one lapse notice
    with app.app_context():
        GkachService.add_balance(db.session.get(WifiVendor, world.vid).user.whatsapp, 1000)
    _login(app, world.uid).post('/wifi/vendor/subscription/renew', headers={'Idempotency-Key': 'renew-key-0002'})
    world.agent.run_once()
    world.agent.run_once()
    assert len(sent) == 2 and 'retabli' in sent[1]                 # exactly one restore notice


# ============================ full lifecycle (fake time) ======================
def _fake_clock_world(world):
    f = Fake(wall=time.time(), mono=5000.0)
    clk = mkclock(world.agent.store, f)
    world.agent.clock, world.agent.engine.now_fn = clk, clk.now
    world.agent.license = world.agent.engine.license = LicenseManager(world.agent.store, clk)
    return f, clk


def test_offline_gateway_sells_through_grace_then_stops_new_sales_but_keeps_paid_sessions(app, world):
    f, clk = _fake_clock_world(world)
    codes = world.generate(4)
    assert world.agent.run_once()['authorized']                         # online: anchored + licensed
    lic = world.agent.status()['license']
    assert lic['state'] == 'ACTIVE' and 2.9 * DAY < lic['seconds_left'] <= 3 * DAY
    world.tr.offline = True                                             # the cloud disappears
    assert call(world.portal, 'POST', '/redeem', 'code=' + codes[0], ip=IP1)[0] == 200
    f.advance(3 * DAY + 3600)                                           # trial over -> GRACE
    assert world.agent.status()['license']['state'] == 'GRACE'
    assert call(world.portal, 'POST', '/redeem', 'code=' + codes[1], ip=IP2)[0] == 200
    f.advance(3 * DAY - 3600 - 600)                                     # 10 minutes before grace ends
    assert call(world.portal, 'POST', '/redeem', 'code=' + codes[2], ip=IP3)[0] == 200
    f.advance(1200)                                                     # grace over
    st = world.agent.status()['license']
    assert st['state'] == 'EXPIRED' and not st['can_sell']
    s, _, body = call(world.portal, 'POST', '/redeem', 'code=' + codes[3], ip=IP2)
    assert s == 503 and 'pa disponib' in body                           # no NEW activation
    assert call(world.portal, 'POST', '/redeem', 'code=' + codes[2], ip=IP3)[0] == 200   # paid session lives on
    assert world.agent.status()['pending_events'] >= 3                  # local history preserved
    f.advance(4000)
    assert IP3 and world.agent.maintain(world.access)                   # ...until its own time runs out
    assert call(world.portal, 'POST', '/redeem', 'code=' + codes[2], ip=IP3)[0] == 400


def test_renewal_restores_full_operation_after_the_next_sync(app, world):
    codes = world.generate(2)
    world.agent.run_once()
    with app.app_context():                                             # subscription lapses on the cloud
        set_policy('offline_grace_days', 0)
        WifiTrial.query.filter_by(vendor_id=world.vid).update({'expires_at': vs.utcnow() - timedelta(days=1)})
        db.session.commit()
    res = world.agent.run_once()
    assert res['access']['state'] == 'EXPIRED'
    assert world.agent.status()['license']['state'] == 'EXPIRED'
    assert call(world.portal, 'POST', '/redeem', 'code=' + codes[0], ip=IP1)[0] == 503
    with app.app_context():                                             # vendor tops up and renews
        GkachService.add_balance(db.session.get(WifiVendor, world.vid).user.whatsapp, 1000)
    assert _login(app, world.uid).post('/wifi/vendor/subscription/renew',
                                       headers={'Idempotency-Key': 'renew-key-0003'}).status_code == 201
    world.agent.run_once()
    assert world.agent.status()['license']['state'] == 'ACTIVE'
    assert call(world.portal, 'POST', '/redeem', 'code=' + codes[0], ip=IP1)[0] == 200


def test_clock_rollback_attack_cannot_extend_a_license_and_is_reported(app, world):
    f, clk = _fake_clock_world(world)
    codes = world.generate(2)
    world.agent.run_once()
    eff = world.agent.status()['license']['effective_until']
    world.tr.offline = True
    assert call(world.portal, 'POST', '/redeem', 'code=' + codes[0], ip=IP1)[0] == 200
    f.wall -= 10 * DAY                                                  # attacker sets the clock back
    f.advance(600)                                                      # (10 real minutes pass)
    world.agent.maintain()                                              # tampering is detected offline
    assert world.agent.status()['license']['state'] == 'UNTRUSTED_CLOCK'
    assert world.agent.status()['license']['effective_until'] == eff    # nothing was extended
    assert call(world.portal, 'POST', '/redeem', 'code=' + codes[1], ip=IP2)[0] == 503     # new sales paused
    assert call(world.portal, 'POST', '/redeem', 'code=' + codes[0], ip=IP1)[0] == 200     # customers unaffected
    world.tr.offline = False
    world.agent.run_once()                                              # next cloud sync
    with app.app_context():
        assert WifiAuditLog.query.filter_by(action='gateway.clock_rollback').count() == 1
    assert world.agent.status()['license']['state'] == 'ACTIVE'
    assert call(world.portal, 'POST', '/redeem', 'code=' + codes[1], ip=IP2)[0] == 200


def test_a_power_cycle_with_a_reset_clock_keeps_time_and_the_license(app, world, tmp_path):
    f, clk = _fake_clock_world(world)
    world.generate(1)
    world.agent.run_once()
    f.advance(1000)
    world.agent.maintain()                                              # persists the high-water mark
    before = clk.now()
    f2 = Fake(wall=1000.0, mono=3.0, boot='boot-2')                     # RTC-less router after power loss
    clk2 = mkclock(Store(str(tmp_path / 'gw' / 'gateway.db')), f2)
    reborn = GatewayAgent(str(tmp_path / 'gw'), 'https://cloud.test', transport=world.tr, clock=clk2)
    assert reborn.clock.now() >= before and reborn.clock.now() < before + 5
    assert reborn.status()['license']['state'] == 'ACTIVE'              # license survived the reboot
    f2.advance(60)
    assert before + 59 <= reborn.clock.now() <= before + 65             # and time keeps flowing


def test_a_replayed_old_cloud_response_cannot_freeze_or_rewind_trusted_time(app, world):
    """Accepting a stale response would re-anchor time in the past; the signed floor would then
    clamp it, FREEZING trusted time (and so every expiry) for as long as the replay is old."""
    f, clk = _fake_clock_world(world)
    world.agent.run_once()                                          # licence installed: floor = its issue time
    before = clk.now()
    world.agent._sync_trust({'server_epoch': int(time.time()) - 86400, 'license': None})
    f.advance(600)
    assert clk.now() >= before + 599                                # still flowing: the replay was refused
