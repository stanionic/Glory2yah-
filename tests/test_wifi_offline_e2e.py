"""End to end: REAL cloud code + REAL agent + portal, with the network cut."""
import os
import sys
import time
from datetime import timedelta

import pytest

os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('SECRET_KEY', 'uwz-tests-secret')
os.environ.setdefault('WTF_CSRF_ENABLED', 'False')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p_ in (ROOT, os.path.join(ROOT, 'tests')):
    if p_ not in sys.path:
        sys.path.insert(0, p_)

from app import create_app, db
from app.wifi import vendor_service as vs
from app.wifi.models import WifiTrial
from app.wifi.policy import set_policy
from gateway_agent.agent import GatewayAgent
from gateway_agent.portal import engine as E
from gateway_agent.portal.access import RecordingController
from gateway_agent.portal.app import PortalApp
from test_wifi_gateway import FlaskTransport, _login, _token
from test_wifi_portal import StubResolver, call
from test_wifi_vouchers import PKG, URL, _gen, _pkg, _vendor

IP1, IP2, IP3 = '192.168.1.50', '192.168.1.51', '192.168.1.52'
MAC1, MAC2, MAC3 = 'aa:bb:cc:00:00:01', 'aa:bb:cc:00:00:02', 'aa:bb:cc:00:00:03'


@pytest.fixture()
def app():
    a = create_app('testing')
    a.config['WTF_CSRF_ENABLED'] = False
    yield a
    with a.app_context():
        db.session.remove()
        db.drop_all()


class World:
    def __init__(self, app, tmp_path):
        self.app, self.tmp = app, tmp_path
        self.uid, self.vid = _vendor(app)
        self.tr = FlaskTransport(app.test_client())
        self.agent = GatewayAgent(str(tmp_path / 'gw'), URL, transport=self.tr)
        self.agent.enroll(_token(app, self.uid, 'Main'))
        self.offset = 0
        self.agent.engine.now_fn = lambda: time.time() + self.offset      # engine clock only
        self.access = RecordingController()
        self.portal = PortalApp(self.agent.engine, self.access,
                                StubResolver({IP1: MAC1, IP2: MAC2, IP3: MAC3}))
        self.vendor = _login(app, self.uid)
        gws = self.vendor.get('/wifi/vendor/gateways').json['gateways']
        self.gid = gws[0]['id']
        self.pid = _pkg(app, self.uid, max_devices=2)

    def generate(self, n=3):
        return _gen(self.app, self.uid, self.pid, self.gid, count=n).json['codes']

    def cloud_voucher(self, code):
        eng = self.agent.engine
        key = eng.store.get('voucher_key')
        uid = eng.store.db.execute('SELECT uid FROM vouchers WHERE hash=?',
                                   (E.hash_code(key, E.normalize_code(code)),)).fetchone()[0]
        return [v for v in self.vendor.get('/wifi/vendor/vouchers').json['vouchers'] if v['uid'] == uid][0]


@pytest.fixture()
def world(app, tmp_path):
    return World(app, tmp_path)


def test_full_offline_sales_cycle_then_reconciliation(world):
    codes = world.generate(3)
    assert world.agent.run_once()['authorized']                         # online: policy synced
    assert world.agent.engine.store.db.execute('SELECT COUNT(*) FROM vouchers').fetchone()[0] == 3

    world.tr.offline = True                                             # --- cloud unreachable ---
    s1, _, b1 = call(world.portal, 'POST', '/redeem', 'code=' + codes[0], ip=IP1)
    s2, _, _ = call(world.portal, 'POST', '/redeem', 'code=' + codes[1], ip=IP2)
    assert (s1, s2) == (200, 200) and 'Ou konekte' in b1
    assert [c[0] for c in world.access.calls] == ['authorize', 'authorize']
    assert world.agent.run_once()['online'] is False                   # offline is normal, no exception
    assert world.agent.status()['pending_events'] == 2

    world.vendor.post(f"/wifi/vendor/vouchers/{world.cloud_voucher(codes[2])['id']}/revoke")
    s3, _, _ = call(world.portal, 'POST', '/redeem', 'code=' + codes[2], ip=IP3)   # gateway does not know yet
    assert s3 == 200                                                    # prepaid/offline sale honoured
    assert world.agent.status()['pending_events'] == 3

    world.tr.offline = False                                            # --- cloud is back ---
    res = world.agent.run_once()
    assert res['synced'] == 3 and res['pending'] == 0
    v1, v2, v3 = (world.cloud_voucher(c) for c in codes)
    assert (v1['status'], v2['status'], v3['status']) == ('REDEEMED', 'REDEEMED', 'REVOKED')
    h = world.vendor.get(f"/wifi/vendor/vouchers/{v1['id']}/redemptions").json['redemptions']
    assert [(r['device'], r['outcome']) for r in h] == [(MAC1, 'ACCEPTED')]
    h3 = world.vendor.get(f"/wifi/vendor/vouchers/{v3['id']}/redemptions").json['redemptions']
    assert [r['outcome'] for r in h3] == ['CONFLICT']                   # recorded, not silently dropped
    assert world.agent.run_once()['synced'] == 0                        # nothing re-sent


def test_gateway_restart_while_offline_loses_nothing(world, tmp_path):
    codes = world.generate(1)
    world.agent.run_once()
    world.tr.offline = True
    call(world.portal, 'POST', '/redeem', 'code=' + codes[0], ip=IP1)
    reborn = GatewayAgent(str(tmp_path / 'gw'), URL, transport=world.tr)       # power cycle
    assert reborn.status()['pending_events'] == 1
    assert [d for d, _ in reborn.engine.active_devices()] == [MAC1]            # can re-authorise after reboot
    world.tr.offline = False
    assert reborn.run_once()['synced'] == 1
    assert world.cloud_voucher(codes[0])['status'] == 'REDEEMED'


def test_sessions_expire_locally_and_are_reported_when_online(world):
    codes = world.generate(1)
    world.agent.run_once()
    world.tr.offline = True
    call(world.portal, 'POST', '/redeem', 'code=' + codes[0], ip=IP1)
    call(world.portal, 'POST', '/redeem', 'code=' + codes[0], ip=IP2)          # 2nd device
    assert world.agent.maintain(world.access) == []                            # still within the hour
    world.offset = 3601
    assert sorted(world.agent.maintain(world.access)) == [MAC1, MAC2]
    assert sorted(c[1] for c in world.access.calls if c[0] == 'deauthorize') == [MAC1, MAC2]
    assert call(world.portal, 'GET', '/status', ip=IP1)[2].count('"active": false') == 1
    assert call(world.portal, 'POST', '/redeem', 'code=' + codes[0], ip=IP1)[0] == 400   # used up
    world.tr.offline = False
    assert world.agent.run_once()['pending'] == 0


def test_a_lapsed_subscription_stops_new_sales_but_not_paid_customers(world, app):
    codes = world.generate(2)
    world.agent.run_once()
    assert call(world.portal, 'POST', '/redeem', 'code=' + codes[0], ip=IP1)[0] == 200
    with app.app_context():                                                     # subscription ends
        set_policy('offline_grace_days', 0)
        WifiTrial.query.filter_by(vendor_id=world.vid).update(
            {'expires_at': vs.utcnow() - timedelta(days=1)})
        db.session.commit()
    res = world.agent.run_once()                                                # gateway learns it
    assert res['access']['can_sell'] is False and res['access']['state'] == 'EXPIRED'
    s, _, body = call(world.portal, 'POST', '/redeem', 'code=' + codes[1], ip=IP2)
    assert s == 503 and 'pa disponib' in body                                   # new activation refused
    assert call(world.portal, 'POST', '/redeem', 'code=' + codes[0], ip=IP1)[0] == 200   # paid customer ok
    row = world.agent.engine.store.db.execute(
        "SELECT status FROM vouchers WHERE hash=?",
        (E.hash_code(world.agent.engine.store.get('voucher_key'), E.normalize_code(codes[1])),)).fetchone()
    assert row[0] == 'unused'                                                   # not consumed


def test_vouchers_for_a_revoked_gateway_stop_syncing(world):
    codes = world.generate(1)
    world.agent.run_once()
    world.vendor.post(f"/wifi/vendor/gateways/{world.gid}/revoke")
    res = world.agent.run_once()
    assert res['authorized'] is False                                           # locked out of the cloud
    assert call(world.portal, 'POST', '/redeem', 'code=' + codes[0], ip=IP1)[0] == 200  # already-synced code
    assert world.agent.status()['revoked'] is True                              # operator is told
