"""Phase 5 cloud side: router inventory reported by gateways."""
import json
import os
import sys
import uuid

import pytest

os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('SECRET_KEY', 'uwz-tests-secret')
os.environ.setdefault('WTF_CSRF_ENABLED', 'False')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p_ in (ROOT, os.path.join(ROOT, 'tests')):
    if p_ not in sys.path:
        sys.path.insert(0, p_)

from app import create_app, db
from app.models.user import User
from app.wifi import vendor_service as vs
from app.wifi.models import WifiRouter
from gateway_agent.agent import GatewayAgent
from gateway_agent.client import CloudUnreachable
from gateway_agent.routers.unsupported import TPLinkAdapter
from gateway_agent.routers.openwrt import OpenWrtAdapter
from gateway_agent.routers.mikrotik import MikroTikAdapter
from sim_routers import FakeOpenWrt, FakeRouterOS
from test_wifi_gateway import FlaskTransport, _login, _token

URL = 'https://cloud.test'
PW_OW, PW_MT = 'correct-horse-battery', 'mt-secret-pass'


@pytest.fixture()
def app():
    a = create_app('testing')
    a.config['WTF_CSRF_ENABLED'] = False
    yield a
    with a.app_context():
        db.session.remove()
        db.drop_all()


def _vendor(app):
    with app.app_context():
        u = User(whatsapp='+5094' + str(uuid.uuid4().int)[:7], pseudo='r' + uuid.uuid4().hex[:10],
                 name='T', auth_provider='whatsapp', is_active=True)
        u.set_password('StrongPass123!')
        db.session.add(u)
        db.session.commit()
        v = vs.register_vendor(u, 'Router Shop')
        return u.id, v.id


def _agent(app, tmp_path, uid, sub='gw'):
    tr = FlaskTransport(app.test_client())
    ag = GatewayAgent(str(tmp_path / sub), URL, transport=tr)
    ag.enroll(_token(app, uid))
    return ag, tr


def _routers(**which):
    ow, mt = FakeOpenWrt(), FakeRouterOS()
    out = {}
    if which.get('ow', True):
        out['ap1'] = OpenWrtAdapter('192.168.1.1', 'apiuser', PW_OW, http=ow.http)
    if which.get('mt', True):
        out['mt1'] = MikroTikAdapter('10.0.0.1', 'api', PW_MT, http=mt.http)
    if which.get('tp', True):
        out['tp1'] = TPLinkAdapter('192.168.0.2')
    return out


def test_inventory_reaches_cloud_dashboard_and_contains_no_secrets(app, tmp_path):
    uid, vid = _vendor(app)
    ag, _ = _agent(app, tmp_path, uid)
    ag.set_routers(_routers())
    res = ag.run_once()
    assert res['authorized'] and res['synced'] == 0
    lst = _login(app, uid).get('/wifi/vendor/routers').json
    assert lst['summary'] == {'total': 3, 'online': 2, 'offline': 0, 'unsupported': 1}
    by = {r['ref']: r for r in lst['routers']}
    assert by['ap1']['kind'] == 'openwrt' and 'wifi_config' in by['ap1']['capabilities']
    assert 'bandwidth' in by['mt1']['capabilities'] and 'bandwidth' not in by['ap1']['capabilities']
    assert by['tp1']['status'] == 'UNSUPPORTED' and by['tp1']['capabilities'] == []
    assert all(r['hardware_verified'] is False for r in lst['routers'])   # simulated only
    blob = json.dumps(lst)
    for secret in (PW_OW, PW_MT, 'apiuser'):
        assert secret not in blob
    dash = _login(app, uid).get('/wifi/vendor/dashboard').json
    assert dash['routers']['total'] == 3 and dash['routers']['online'] == 2


def test_report_is_a_replace_set_and_status_changes_are_tracked(app, tmp_path):
    uid, vid = _vendor(app)
    ag, _ = _agent(app, tmp_path, uid)
    ag.set_routers(_routers())
    ag.run_once()
    ag.set_routers(_routers(mt=False))                       # mt1 removed from config
    ag.run_once()
    lst = _login(app, uid).get('/wifi/vendor/routers').json
    assert sorted(r['ref'] for r in lst['routers']) == ['ap1', 'tp1']
    # an unreachable router becomes OFFLINE (not deleted, not crashing the agent)
    # wrong credentials -> the router cannot be queried -> OFFLINE, agent keeps running
    down = OpenWrtAdapter('192.168.1.1', 'apiuser', 'wrong-password-xx', http=FakeOpenWrt().http)
    ag.set_routers({'ap1': down, 'tp1': TPLinkAdapter('192.168.0.2')})
    ag.run_once()
    lst = _login(app, uid).get('/wifi/vendor/routers').json
    st = {r['ref']: r for r in lst['routers']}
    assert st['ap1']['status'] == 'OFFLINE' and st['ap1']['error'] and lst['summary']['offline'] == 1


def test_inventory_is_isolated_between_vendors_and_admin_sees_all(app, tmp_path):
    ua, va = _vendor(app)
    ub, vb = _vendor(app)
    ga, _ = _agent(app, tmp_path, ua, 'a')
    gb, _ = _agent(app, tmp_path, ub, 'b')
    ga.set_routers({'ap1': _routers()['ap1']})
    gb.set_routers({'tp1': TPLinkAdapter('192.168.0.2')})
    ga.run_once()
    gb.run_once()
    ra = _login(app, ua).get('/wifi/vendor/routers').json['routers']
    rb = _login(app, ub).get('/wifi/vendor/routers').json['routers']
    assert [r['ref'] for r in ra] == ['ap1'] and [r['ref'] for r in rb] == ['tp1']
    with app.app_context():
        admin = User(whatsapp='+5094' + str(uuid.uuid4().int)[:7], pseudo='a' + uuid.uuid4().hex[:8],
                     name='A', is_active=True, is_admin=True)
        admin.set_password('StrongPass123!')
        db.session.add(admin)
        db.session.commit()
        aid = admin.id
    allr = _login(app, aid).get('/wifi/admin/routers').json['routers']
    assert {(r['ref'], r['vendor_id']) for r in allr} == {('ap1', va), ('tp1', vb)}
    assert _login(app, ua).get('/wifi/admin/routers').status_code in (302, 401, 403)


def _post(app, ag, routers):
    body = json.dumps({'routers': routers}).encode()
    h = ag.client.sign_headers('POST', '/wifi/gateway/routers', body)
    return app.test_client().post('/wifi/gateway/routers', data=body, headers=h)


def test_cloud_validates_and_sanitises_router_reports(app, tmp_path):
    uid, vid = _vendor(app)
    ag, _ = _agent(app, tmp_path, uid)
    ok = {'ref': 'r1', 'kind': 'openwrt', 'status': 'ONLINE', 'support_level': 'implemented',
          'capabilities': ['info', 'wifi_config', 'launch_missiles'], 'vendor_id': 9999,
          'model': 'M' * 500}
    assert _post(app, ag, [ok]).status_code == 200
    with app.app_context():
        row = WifiRouter.query.one()
        assert json.loads(row.capabilities) == ['info', 'wifi_config']     # unknown filtered
        assert row.vendor_id == vid and len(row.model) == 80               # clamped, tenant from key
    bad_cases = [
        [dict(ok, status='HACKED')], [dict(ok, ref='bad ref!')], [dict(ok), dict(ok)],
        [dict(ok, ref=f'r{i}') for i in range(51)], 'nope', [1, 2],
    ]
    for case in bad_cases:
        assert _post(app, ag, case).status_code == 400, case
    with app.app_context():
        assert WifiRouter.query.count() == 1                 # rejected reports changed nothing


def test_router_endpoint_requires_a_valid_signature(app, tmp_path):
    uid, vid = _vendor(app)
    ag, _ = _agent(app, tmp_path, uid)
    assert app.test_client().post('/wifi/gateway/routers', json={'routers': []}).status_code == 401
    body = b'{"routers":[]}'
    h = ag.client.sign_headers('POST', '/wifi/gateway/heartbeat', body)    # wrong path signed
    assert app.test_client().post('/wifi/gateway/routers', data=body, headers=h).status_code == 401


def test_offline_agent_keeps_a_local_inventory_copy_and_never_raises(app, tmp_path):
    uid, vid = _vendor(app)
    ag, tr = _agent(app, tmp_path, uid)
    ag.set_routers(_routers())
    tr.offline = True
    assert ag.run_once()['online'] is False                   # normal offline behaviour
    with pytest.raises(CloudUnreachable):
        ag.report_routers()                                   # direct call surfaces the network error
    local = ag.store.get('router_inventory')
    assert {i['ref'] for i in local} == {'ap1', 'mt1', 'tp1'}  # but the snapshot is kept locally
    tr.offline = False
    ag.run_once()
    assert _login(app, uid).get('/wifi/vendor/routers').json['summary']['total'] == 3
