"""Phase 6 cloud half: packages, portal config, vouchers, policy sync, redemption events."""
import base64
import json
import os
import re
import sys
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

from app import create_app, db
from app.models.user import User
from app.wifi import vendor_service as vs
from app.wifi import voucher_service as vsv
from app.wifi.models import (WifiAuditLog, WifiGateway, WifiGatewayKey, WifiOfflineEvent,
                             WifiTrial, WifiVoucher, WifiVoucherRedemption)
from app.wifi.policy import set_policy
from gateway_agent.agent import GatewayAgent
from test_wifi_gateway import FlaskTransport, _login, _token

URL = 'https://cloud.test'
CODE_RE = re.compile(r'^[2-9A-HJKMNP-Z]{4}-[2-9A-HJKMNP-Z]{4}-[2-9A-HJKMNP-Z]{4}$')


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
        u = User(whatsapp='+5094' + str(uuid.uuid4().int)[:7], pseudo='v' + uuid.uuid4().hex[:10],
                 name='T', auth_provider='whatsapp', is_active=True)
        u.set_password('StrongPass123!')
        db.session.add(u)
        db.session.commit()
        v = vs.register_vendor(u, 'Voucher Shop')
        return u.id, v.id


def _gw(app, tmp_path, uid, sub):
    ag = GatewayAgent(str(tmp_path / sub), URL, transport=FlaskTransport(app.test_client()))
    ag.enroll(_token(app, uid, f'GW {sub}'))
    gid = [g for g in _login(app, uid).get('/wifi/vendor/gateways').json['gateways']
           if g['gateway_uid'] == ag.store.get('gateway_uid')][0]['id']
    return ag, gid


PKG = {'name': '1 Hour', 'price_gkach': 50, 'duration_minutes': 60, 'down_kbps': 2000,
       'up_kbps': 1000, 'max_devices': 2, 'voucher_valid_days': 30}


def _pkg(app, uid, **over):
    r = _login(app, uid).post('/wifi/vendor/packages', json=dict(PKG, **over))
    assert r.status_code == 201, r.json
    return r.json['id']


def _gen(app, uid, pid, gid, **over):
    return _login(app, uid).post('/wifi/vendor/vouchers/generate',
                                 json=dict({'package_id': pid, 'gateway_id': gid, 'count': 3}, **over))


@pytest.fixture()
def shop(app, tmp_path):
    uid, vid = _vendor(app)
    ag, gid = _gw(app, tmp_path, uid, 'g1')
    return {'uid': uid, 'vid': vid, 'ag': ag, 'gid': gid, 'pid': _pkg(app, uid)}


# --------------------------------- packages ---------------------------------
@pytest.mark.parametrize('bad', [
    {'name': 'x'}, {'name': ''}, {'duration_minutes': 0}, {'duration_minutes': 525601},
    {'price_gkach': -1}, {'price_gkach': True}, {'price_gkach': '50'}, {'max_devices': 0},
    {'max_devices': 11}, {'down_kbps': 10}, {'up_kbps': 2_000_000}, {'data_mb': 0},
    {'voucher_valid_days': 0}, {'voucher_valid_days': 366},
])
def test_package_validation(app, shop, bad):
    r = _login(app, shop['uid']).post('/wifi/vendor/packages', json=dict(PKG, name='Other', **bad)
                                      if 'name' not in bad else dict(PKG, **bad))
    assert r.status_code == 400, (bad, r.json)


def test_package_requires_duration_and_rejects_duplicate_names(app, shop):
    c = _login(app, shop['uid'])
    assert c.post('/wifi/vendor/packages', json={'name': 'No Duration'}).status_code == 400
    assert c.post('/wifi/vendor/packages', json=PKG).status_code == 409


def test_package_unlimited_fields_and_update(app, shop):
    c = _login(app, shop['uid'])
    r = c.post('/wifi/vendor/packages', json={'name': 'Unlimited', 'duration_minutes': 1440})
    assert r.status_code == 201 and r.json['data_mb'] is None and r.json['down_kbps'] is None
    pid = r.json['id']
    u = c.patch(f'/wifi/vendor/packages/{pid}', json={'price_gkach': 120, 'is_active': False})
    assert u.status_code == 200 and u.json['price_gkach'] == 120 and u.json['is_active'] is False
    assert c.patch(f'/wifi/vendor/packages/{pid}', json={}).status_code == 400
    assert c.patch(f'/wifi/vendor/packages/{pid}', json={'is_active': 'no'}).status_code == 400


def test_packages_are_isolated_between_vendors(app, shop, tmp_path):
    ub, vb = _vendor(app)
    other = _login(app, ub)
    assert other.get('/wifi/vendor/packages').json['packages'] == []
    assert other.patch(f"/wifi/vendor/packages/{shop['pid']}", json={'price_gkach': 1}).status_code == 404
    assert other.post('/wifi/vendor/packages', json=PKG).status_code == 201        # same name is fine
    mine = _login(app, shop['uid']).get('/wifi/vendor/packages').json['packages']
    assert [p['price_gkach'] for p in mine] == [50]


# -------------------------------- portal config -----------------------------
def test_portal_defaults_and_update(app, shop):
    c = _login(app, shop['uid'])
    d = c.get('/wifi/vendor/portal').json
    assert d['brand_name'] == 'Voucher Shop' and d['voucher_enabled'] and not d['free_access_enabled']
    r = c.put('/wifi/vendor/portal', json={'brand_name': 'Cyber Mapou', 'brand_color': '#112233',
                                           'welcome_text': 'Byenveni!'})
    assert r.status_code == 200 and r.json['brand_name'] == 'Cyber Mapou'


@pytest.mark.parametrize('bad', [
    {'brand_color': 'red'}, {'brand_color': '#12345'}, {'brand_color': 'url(x)'},
    {'brand_name': 'x'}, {'brand_name': 'a\x00b'}, {'welcome_text': 'x' * 241},
    {'free_cooldown_hours': 0}, {'voucher_enabled': 'yes'}, {'free_access_enabled': True},
])
def test_portal_validation(app, shop, bad):
    assert _login(app, shop['uid']).put('/wifi/vendor/portal', json=bad).status_code == 400


def test_free_access_needs_an_own_active_zero_price_package(app, shop):
    c = _login(app, shop['uid'])
    free = c.post('/wifi/vendor/packages', json={'name': 'Free 15m', 'duration_minutes': 15,
                                                 'price_gkach': 0}).json['id']
    ub, vb = _vendor(app)
    foreign_free = _login(app, ub).post('/wifi/vendor/packages', json={
        'name': 'Theirs', 'duration_minutes': 15, 'price_gkach': 0}).json['id']
    for pid in (shop['pid'], foreign_free, 99999):          # paid / not mine / missing
        assert c.put('/wifi/vendor/portal', json={'free_access_enabled': True,
                                                  'free_package_id': pid}).status_code == 400
    ok = c.put('/wifi/vendor/portal', json={'free_access_enabled': True, 'free_package_id': free})
    assert ok.status_code == 200 and ok.json['free_package_id'] == free


# --------------------------------- generation --------------------------------
def test_generated_codes_are_well_formed_unique_and_shown_once(app, shop):
    r = _gen(app, shop['uid'], shop['pid'], shop['gid'], count=50)
    assert r.status_code == 201 and r.headers['Cache-Control'] == 'no-store'
    codes = r.json['codes']
    assert len(codes) == len(set(codes)) == 50 and all(CODE_RE.match(c) for c in codes)
    assert 'ONCE' in r.json['note']
    # listing never returns codes or hashes
    lst = _login(app, shop['uid']).get('/wifi/vendor/vouchers').json['vouchers']
    blob = json.dumps(lst)
    assert len(lst) == 50 and 'hash' not in blob and not any(c in blob for c in codes)
    assert all(set(v) == {'id', 'uid', 'status', 'package_id', 'gateway_id', 'batch_id', 'label',
                          'expires_at', 'redeemed_at'} for v in lst)


def test_only_keyed_hashes_are_stored_never_the_code(app, shop):
    codes = _gen(app, shop['uid'], shop['pid'], shop['gid'], count=5).json['codes']
    with app.app_context():
        key = WifiGatewayKey.query.one().voucher_key
        stored = {v.code_hash for v in WifiVoucher.query}
        for c in codes:
            norm = vsv.normalize_code(c)
            assert vsv.hash_code(key, norm) in stored
            for row in WifiVoucher.query:                      # plaintext nowhere in the row
                assert norm not in json.dumps([str(getattr(row, col.name)) for col in row.__table__.columns])
            assert not any(norm in (a.detail or '') for a in WifiAuditLog.query)
        # a different gateway key yields different hashes for the same code
        other = base64.b64encode(os.urandom(32)).decode()
        assert vsv.hash_code(other, vsv.normalize_code(codes[0])) not in stored


@pytest.mark.parametrize('count', [0, 501, -1, '5', True, None, 1.5])
def test_generation_count_limits(app, shop, count):
    assert _gen(app, shop['uid'], shop['pid'], shop['gid'], count=count).status_code == 400


def test_generation_respects_ownership_and_state(app, shop, tmp_path):
    ub, vb = _vendor(app)
    bag, bgid = _gw(app, tmp_path, ub, 'gb')
    bpid = _pkg(app, ub)
    c = _login(app, shop['uid'])
    assert _gen(app, shop['uid'], shop['pid'], bgid).status_code == 404     # foreign gateway
    assert _gen(app, shop['uid'], bpid, shop['gid']).status_code == 404     # foreign package
    assert c.post('/wifi/vendor/vouchers/generate', json={'package_id': 'x', 'gateway_id': 1}).status_code == 400
    c.patch(f"/wifi/vendor/packages/{shop['pid']}", json={'is_active': False})
    assert _gen(app, shop['uid'], shop['pid'], shop['gid']).status_code == 409      # inactive package
    c.patch(f"/wifi/vendor/packages/{shop['pid']}", json={'is_active': True})
    assert c.post(f"/wifi/vendor/gateways/{shop['gid']}/revoke").status_code == 200
    assert _gen(app, shop['uid'], shop['pid'], shop['gid']).status_code == 409      # revoked gateway
    with app.app_context():
        assert WifiVoucher.query.count() == 0


def test_generation_blocked_when_subscription_expired(app, shop):
    with app.app_context():
        set_policy('offline_grace_days', 0)
        WifiTrial.query.filter_by(vendor_id=shop['vid']).update(
            {'expires_at': vs.utcnow() - timedelta(days=1)})
        db.session.commit()
    r = _gen(app, shop['uid'], shop['pid'], shop['gid'])
    assert r.status_code == 402
    with app.app_context():
        assert WifiVoucher.query.count() == 0


def test_voucher_expiry_is_the_earlier_of_package_and_request(app, shop):
    short = _gen(app, shop['uid'], shop['pid'], shop['gid'], count=1, expires_in_days=3).json
    longer = _gen(app, shop['uid'], shop['pid'], shop['gid'], count=1, expires_in_days=300).json
    now = vs.utcnow()
    from datetime import datetime
    d = lambda r: (datetime.fromisoformat(r['expires_at']) - now).total_seconds() / 86400
    assert 2.9 < d(short) < 3.1 and 29.9 < d(longer) < 30.1      # package cap (30d) wins over 300


# ----------------------------- list / revoke / isolation ----------------------
def test_revoke_rules_and_isolation(app, shop):
    _gen(app, shop['uid'], shop['pid'], shop['gid'], count=3)
    c = _login(app, shop['uid'])
    lst = c.get('/wifi/vendor/vouchers').json['vouchers']
    vid = lst[0]['id']
    ub, vb = _vendor(app)
    assert _login(app, ub).post(f'/wifi/vendor/vouchers/{vid}/revoke').status_code == 404
    assert _login(app, ub).get('/wifi/vendor/vouchers').json['vouchers'] == []
    assert c.post(f'/wifi/vendor/vouchers/{vid}/revoke').json['status'] == 'REVOKED'
    assert c.post(f'/wifi/vendor/vouchers/{vid}/revoke').status_code == 409
    assert len(c.get('/wifi/vendor/vouchers?status=revoked').json['vouchers']) == 1
    with app.app_context():
        WifiVoucher.query.filter_by(id=lst[1]['id']).update({'status': 'REDEEMED'})
        db.session.commit()
    assert c.post(f"/wifi/vendor/vouchers/{lst[1]['id']}/revoke").status_code == 409


# --------------------------------- policy sync --------------------------------
def _policy(app, ag, cursor=0):
    body = json.dumps({'cursor': cursor}).encode()
    h = ag.client.sign_headers('POST', '/wifi/gateway/sync-policy', body)
    return app.test_client().post('/wifi/gateway/sync-policy', data=body, headers=h)


def test_policy_requires_a_valid_signature(app, shop):
    assert app.test_client().post('/wifi/gateway/sync-policy', json={}).status_code == 401


def test_policy_contains_only_this_gateways_vouchers_and_matches_codes(app, shop, tmp_path):
    ag2, gid2 = _gw(app, tmp_path, shop['uid'], 'g2')
    ub, vb = _vendor(app)
    bag, bgid = _gw(app, tmp_path, ub, 'gb')
    codes1 = _gen(app, shop['uid'], shop['pid'], shop['gid'], count=3).json['codes']
    _gen(app, shop['uid'], shop['pid'], gid2, count=4)
    _gen(app, ub, _pkg(app, ub), bgid, count=5)
    p1 = _policy(app, shop['ag']).json
    p2 = _policy(app, ag2).json
    assert len(p1['vouchers']) == 3 and len(p2['vouchers']) == 4
    assert p1['voucher_key'] != p2['voucher_key']                       # per-gateway secret
    assert {v['uid'] for v in p1['vouchers']}.isdisjoint({v['uid'] for v in p2['vouchers']})
    assert _policy(app, shop['ag']).json['voucher_key'] == p1['voucher_key']       # stable
    hashes = {v['hash'] for v in p1['vouchers']}
    for c in codes1:                                    # the gateway can verify a typed code offline
        assert vsv.hash_code(p1['voucher_key'], vsv.normalize_code(c)) in hashes
        assert vsv.hash_code(p2['voucher_key'], vsv.normalize_code(c)) not in hashes
    assert [p['name'] for p in p1['packages']] == ['1 Hour']
    assert p1['access']['can_sell'] is True and p1['portal']['brand_name'] == 'Voucher Shop'


def test_policy_sends_revoked_but_not_redeemed_and_only_active_packages(app, shop):
    _gen(app, shop['uid'], shop['pid'], shop['gid'], count=3)
    c = _login(app, shop['uid'])
    ids = [v['id'] for v in c.get('/wifi/vendor/vouchers').json['vouchers']]
    c.post(f'/wifi/vendor/vouchers/{ids[0]}/revoke')
    with app.app_context():
        WifiVoucher.query.filter_by(id=ids[1]).update({'status': 'REDEEMED'})
        db.session.commit()
    c.patch(f"/wifi/vendor/packages/{shop['pid']}", json={'is_active': False})
    p = _policy(app, shop['ag']).json
    assert sorted(v['status'] for v in p['vouchers']) == ['REVOKED', 'UNUSED']
    assert p['packages'] == []


def test_policy_cursor_pagination_and_validation(app, shop):
    _gen(app, shop['uid'], shop['pid'], shop['gid'], count=5)
    with app.app_context():
        gw = WifiGateway.query.one()
        from app.wifi.models import WifiVendor
        vend = db.session.get(WifiVendor, gw.vendor_id)
        seen, cursor = [], 0
        for _ in range(10):
            page = vsv.build_policy(gw, vend, cursor=cursor, limit=2)
            seen += [v['uid'] for v in page['vouchers']]
            cursor = page['next_cursor']
            if cursor is None:
                break
        assert len(seen) == len(set(seen)) == 5
    for bad in (-1, True, 'a', 1.5):
        assert _policy(app, shop['ag'], bad).status_code == 400


# ------------------------------ redemption events -----------------------------
def _uids(app, uid):
    return [v['uid'] for v in _login(app, uid).get('/wifi/vendor/vouchers').json['vouchers']]


def _redeem_event(ag, uid, mac='aa:bb:cc:00:00:01', **over):
    p = {'voucher_uid': uid, 'device': mac, 'redeemed_at': '2026-11-12T10:00:00Z',
         'ends_at': '2026-11-12T11:00:00Z'}
    p.update(over)
    return ag.record_event('voucher.redeemed', p)


def test_redemption_event_marks_voucher_redeemed_with_history(app, shop):
    _gen(app, shop['uid'], shop['pid'], shop['gid'], count=2)
    uid1 = _uids(app, shop['uid'])[0]
    _redeem_event(shop['ag'], uid1)
    assert shop['ag'].run_once()['synced'] == 1
    c = _login(app, shop['uid'])
    v = [x for x in c.get('/wifi/vendor/vouchers').json['vouchers'] if x['uid'] == uid1][0]
    assert v['status'] == 'REDEEMED' and v['redeemed_at'].startswith('2026-11-12T10:00')
    h = c.get(f"/wifi/vendor/vouchers/{v['id']}/redemptions").json
    assert [(r['device'], r['outcome']) for r in h['redemptions']] == [('aa:bb:cc:00:00:01', 'ACCEPTED')]
    with app.app_context():
        assert WifiOfflineEvent.query.one().processed_at is not None


def test_redemption_is_idempotent_across_resends(app, shop):
    _gen(app, shop['uid'], shop['pid'], shop['gid'], count=1)
    uid1 = _uids(app, shop['uid'])[0]
    eid = _redeem_event(shop['ag'], uid1)
    ev = [{'event_id': eid, 'seq': 0, 'type': 'voucher.redeemed', 'payload': {
        'voucher_uid': uid1, 'device': 'aa:bb:cc:00:00:01',
        'redeemed_at': '2026-11-12T10:00:00Z', 'ends_at': '2026-11-12T11:00:00Z'}}]
    body = json.dumps({'events': ev}).encode()
    for _ in range(3):
        h = shop['ag'].client.sign_headers('POST', '/wifi/gateway/sync', body)
        assert app.test_client().post('/wifi/gateway/sync', data=body, headers=h).status_code == 200
    with app.app_context():
        assert WifiVoucherRedemption.query.count() == 1 and WifiOfflineEvent.query.count() == 1


def test_second_device_adds_history_without_changing_status(app, shop):
    _gen(app, shop['uid'], shop['pid'], shop['gid'], count=1)
    uid1 = _uids(app, shop['uid'])[0]
    _redeem_event(shop['ag'], uid1, 'aa:bb:cc:00:00:01')
    _redeem_event(shop['ag'], uid1, 'aa:bb:cc:00:00:02')
    shop['ag'].run_once()
    with app.app_context():
        v = WifiVoucher.query.one()
        assert v.status == 'REDEEMED'
        assert sorted(r.device_mac for r in WifiVoucherRedemption.query) == [
            'aa:bb:cc:00:00:01', 'aa:bb:cc:00:00:02']


def test_foreign_and_unknown_vouchers_cannot_be_redeemed_by_another_gateway(app, shop, tmp_path):
    ub, vb = _vendor(app)
    bag, bgid = _gw(app, tmp_path, ub, 'gb')
    ag2, gid2 = _gw(app, tmp_path, shop['uid'], 'g2')               # same vendor, other gateway
    _gen(app, ub, _pkg(app, ub), bgid, count=1)
    _gen(app, shop['uid'], shop['pid'], shop['gid'], count=1)
    their = _uids(app, ub)[0]
    mine_on_g1 = _uids(app, shop['uid'])[0]
    _redeem_event(shop['ag'], their)                                 # vendor A's gateway -> B's voucher
    _redeem_event(ag2, mine_on_g1)                                   # same vendor, WRONG gateway
    _redeem_event(shop['ag'], 'v_0000000000')                        # unknown
    for a in (shop['ag'], ag2):
        a.run_once()
    with app.app_context():
        assert {v.status for v in WifiVoucher.query} == {'UNUSED'}   # nothing changed
        assert WifiVoucherRedemption.query.count() == 0
        assert WifiAuditLog.query.filter_by(action='voucher.redemption_rejected').count() == 3
        assert WifiOfflineEvent.query.count() == 3                   # raw events still kept


@pytest.mark.parametrize('payload', [
    {'voucher_uid': 'nope', 'device': 'aa:bb:cc:00:00:01'},
    {'voucher_uid': 'v_abcdef0123', 'device': 'not-a-mac'},
    {'voucher_uid': 123, 'device': 'aa:bb:cc:00:00:01'},
    {'device': 'aa:bb:cc:00:00:01'},
])
def test_malformed_redemption_payloads_are_rejected_without_breaking_sync(app, shop, payload):
    shop['ag'].record_event('voucher.redeemed', payload)
    ok = shop['ag'].record_event('gateway.event', {'still': 'processed'})
    r = shop['ag'].run_once()
    assert r['synced'] == 2 and r['pending'] == 0                    # a bad event never blocks the queue
    with app.app_context():
        assert WifiVoucherRedemption.query.count() == 0


def test_voucher_revoked_before_sync_is_recorded_as_conflict_and_stays_revoked(app, shop):
    _gen(app, shop['uid'], shop['pid'], shop['gid'], count=1)
    c = _login(app, shop['uid'])
    v = c.get('/wifi/vendor/vouchers').json['vouchers'][0]
    c.post(f"/wifi/vendor/vouchers/{v['id']}/revoke")
    _redeem_event(shop['ag'], v['uid'])                              # customer used it while offline
    shop['ag'].run_once()
    h = c.get(f"/wifi/vendor/vouchers/{v['id']}/redemptions").json
    assert h['voucher']['status'] == 'REVOKED'
    assert [(r['outcome'], 'revoked' in r['note']) for r in h['redemptions']] == [('CONFLICT', True)]


def test_redemption_history_is_private_to_the_vendor(app, shop):
    _gen(app, shop['uid'], shop['pid'], shop['gid'], count=1)
    vid = _login(app, shop['uid']).get('/wifi/vendor/vouchers').json['vouchers'][0]['id']
    ub, vb = _vendor(app)
    assert _login(app, ub).get(f'/wifi/vendor/vouchers/{vid}/redemptions').status_code == 404
    assert app.test_client().get(f'/wifi/vendor/vouchers/{vid}/redemptions').status_code == 401
