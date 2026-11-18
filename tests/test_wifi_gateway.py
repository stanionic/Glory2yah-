"""Phase 4 tests: gateway enrollment, signed auth, offline queue, idempotent sync.

The REAL agent talks to the REAL cloud code through FlaskTransport.
"""
import os
import sys
import time
import uuid
from datetime import timedelta
from urllib.parse import urlparse

import pytest

os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('SECRET_KEY', 'uwz-tests-secret')
os.environ.setdefault('WTF_CSRF_ENABLED', 'False')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app import create_app, db
from app.models.user import User
from app.wifi import gateway_service as gs
from app.wifi import vendor_service as vs
from app.wifi.models import (WifiGateway, WifiGatewayEnrollment, WifiGatewayNonce,
                             WifiOfflineEvent, WifiTrial, WifiVendor)
from app.wifi.policy import set_policy
from gateway_agent.agent import GatewayAgent
from gateway_agent.client import CloudClient, CloudRejected, CloudUnreachable, UrllibTransport
from gateway_agent.store import Store

URL = 'https://cloud.test'


class FlaskTransport:
    def __init__(self, client):
        self.client, self.offline = client, False

    def request(self, method, url, headers, body):
        if self.offline:
            raise CloudUnreachable('network down')
        r = self.client.open(urlparse(url).path, method=method, data=body, headers=headers)
        return r.status_code, r.data


@pytest.fixture()
def app():
    a = create_app('testing')
    a.config['WTF_CSRF_ENABLED'] = False
    yield a
    with a.app_context():
        db.session.remove()
        db.drop_all()


def _vendor_user():
    u = User(whatsapp='+5094' + str(uuid.uuid4().int)[:7], pseudo='g' + uuid.uuid4().hex[:10],
             name='T', auth_provider='whatsapp', is_active=True)
    u.set_password('StrongPass123!')
    db.session.add(u)
    db.session.commit()
    v = vs.register_vendor(u, 'Gateway Shop')
    return u.id, v.id


def _login(app, uid):
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(uid)
        s['_fresh'] = True
    return c


def _token(app, uid, name='Main GW'):
    r = _login(app, uid).post('/wifi/vendor/gateways/enrollment-tokens', json={'name': name})
    assert r.status_code == 201, r.json
    return r.json['token']


def _agent(app, tmp_path, uid, name='Main GW', sub='gw'):
    tr = FlaskTransport(app.test_client())
    ag = GatewayAgent(str(tmp_path / sub), URL, transport=tr)
    ag.enroll(_token(app, uid, name))
    return ag, tr


@pytest.fixture()
def vend(app):
    with app.app_context():
        return _vendor_user()


# ------------------------------- enrollment ---------------------------------
def test_token_is_single_use_and_stored_hashed(app, vend, tmp_path):
    uid, vid = vend
    tok = _token(app, uid)
    with app.app_context():
        row = WifiGatewayEnrollment.query.one()
        assert row.token_hash == gs.hash_token(tok) and tok not in (row.token_hash, row.name)
    a1 = GatewayAgent(str(tmp_path / 'a1'), URL, transport=FlaskTransport(app.test_client()))
    out = a1.enroll(tok)
    assert out['gateway_uid'].startswith('gw_') and a1.enrolled
    a2 = GatewayAgent(str(tmp_path / 'a2'), URL, transport=FlaskTransport(app.test_client()))
    with pytest.raises(CloudRejected) as e:
        a2.enroll(tok)
    assert e.value.status == 401 and not a2.enrolled


def test_expired_unknown_and_garbage_tokens_get_same_error(app, vend, tmp_path):
    uid, vid = vend
    tok = _token(app, uid)
    with app.app_context():
        WifiGatewayEnrollment.query.update({'expires_at': vs.utcnow() - timedelta(seconds=1)})
        db.session.commit()
    errs = []
    for t in (tok, 'uwz1_doesnotexist', ''):
        ag = GatewayAgent(str(tmp_path / uuid.uuid4().hex), URL,
                          transport=FlaskTransport(app.test_client()))
        with pytest.raises(CloudRejected) as e:
            ag.enroll(t)
        errs.append((e.value.status, str(e.value)))
    assert len(set(errs)) == 1 and errs[0][0] == 401        # no oracle


def test_enrollment_binds_public_key_and_private_key_stays_local(app, vend, tmp_path):
    ag, _ = _agent(app, tmp_path, vend[0])
    from gateway_agent import keys
    keyfile = tmp_path / 'gw' / keys.KEY_FILE
    assert oct(os.stat(keyfile).st_mode & 0o777) == '0o600'
    with app.app_context():
        gw = WifiGateway.query.one()
        assert gw.public_key == keys.public_b64(ag.key) and gw.vendor_id == vend[1]
        priv = open(keyfile, 'rb').read().decode()
        for col in (gw.public_key, gw.name, gw.gateway_uid):
            assert priv not in col                     # cloud never holds the private key
    assert ag.store.get('cloud_public_key')            # kept for offline licenses
    # key survives restart (same identity)
    again = GatewayAgent(str(tmp_path / 'gw'), URL, transport=FlaskTransport(app.test_client()))
    assert keys.public_b64(again.key) == keys.public_b64(ag.key) and again.enrolled


def test_invalid_and_duplicate_public_keys_rejected(app, vend):
    c = app.test_client()
    tok = _token(app, vend[0])
    assert c.post('/wifi/gateway/enroll', json={'token': tok, 'public_key': 'nope'}).status_code == 400
    from gateway_agent import keys
    pub = keys.public_b64(Ed25519PrivateKey.generate())
    assert c.post('/wifi/gateway/enroll', json={'token': tok, 'public_key': pub}).status_code == 201
    tok2 = _token(app, vend[0], 'Second')
    assert c.post('/wifi/gateway/enroll', json={'token': tok2, 'public_key': pub}).status_code == 409


def test_enrollment_503_when_production_has_no_signing_key(app, vend, monkeypatch):
    monkeypatch.delenv('UWZ_LICENSE_SIGNING_KEY', raising=False)
    tok = _token(app, vend[0])
    app.config['TESTING'] = False
    app.debug = False
    from gateway_agent import keys
    r = app.test_client().post('/wifi/gateway/enroll', json={
        'token': tok, 'public_key': keys.public_b64(Ed25519PrivateKey.generate())})
    assert r.status_code == 503


def test_token_needs_active_plan_and_respects_gateway_limit(app, vend):
    uid, vid = vend
    set_policy_ctx = lambda k, v: (set_policy(k, v), db.session.commit())
    with app.app_context():
        set_policy_ctx('max_gateways_per_vendor', 1)
    _agent_ok = _login(app, uid).post('/wifi/vendor/gateways/enrollment-tokens', json={'name': 'One'})
    tok = _agent_ok.json['token']
    from gateway_agent import keys
    app.test_client().post('/wifi/gateway/enroll', json={
        'token': tok, 'public_key': keys.public_b64(Ed25519PrivateKey.generate())})
    assert _login(app, uid).post('/wifi/vendor/gateways/enrollment-tokens',
                                 json={'name': 'Two'}).status_code == 409
    with app.app_context():
        set_policy_ctx('max_gateways_per_vendor', 3)
        set_policy_ctx('offline_grace_days', 0)
        WifiTrial.query.filter_by(vendor_id=vid).update({'expires_at': vs.utcnow() - timedelta(days=1)})
        db.session.commit()
    assert _login(app, uid).post('/wifi/vendor/gateways/enrollment-tokens',
                                 json={'name': 'Three'}).status_code == 402


# ----------------------------- signed authentication ------------------------
def _raw(app, ag, body=b'{}', headers=None, path='/wifi/gateway/heartbeat'):
    h = headers or ag.client.sign_headers('POST', path, body)
    return app.test_client().post(path, data=body, headers=h)


def test_valid_signature_heartbeat_returns_access_and_server_time(app, vend, tmp_path):
    ag, _ = _agent(app, tmp_path, vend[0])
    res = ag.run_once()
    assert res['online'] and res['authorized'] and res['access']['state'] == 'TRIAL'
    st = ag.status()
    assert st['last_cloud_ok_epoch'] and abs(st['cloud_clock_offset_s']) < 5
    with app.app_context():
        assert WifiGateway.query.one().last_seen_at is not None


def test_bad_signatures_replay_and_stale_timestamps_are_rejected(app, vend, tmp_path):
    ag, _ = _agent(app, tmp_path, vend[0])
    assert _raw(app, ag).status_code == 200
    # tampered body: signed for A, sent as B
    h = ag.client.sign_headers('POST', '/wifi/gateway/sync', b'{"events":[]}')
    assert _raw(app, ag, b'{"events":[1]}', h, '/wifi/gateway/sync').status_code == 401
    # replay of an exact captured request
    h = ag.client.sign_headers('POST', '/wifi/gateway/heartbeat', b'{}')
    assert _raw(app, ag, headers=h).status_code == 200
    assert _raw(app, ag, headers=h).status_code == 401
    # old timestamp
    old = CloudClient(URL, ag.key, ag.client.gateway_uid, now_fn=lambda: time.time() - 1000)
    assert _raw(app, ag, headers=old.sign_headers('POST', '/wifi/gateway/heartbeat', b'{}')).status_code == 401
    # an attacker key claiming to be this gateway
    evil = CloudClient(URL, Ed25519PrivateKey.generate(), ag.client.gateway_uid)
    assert _raw(app, ag, headers=evil.sign_headers('POST', '/wifi/gateway/heartbeat', b'{}')).status_code == 401
    # signature for another path cannot be reused
    h = ag.client.sign_headers('POST', '/wifi/gateway/heartbeat', b'{}')
    assert _raw(app, ag, b'{}', h, '/wifi/gateway/sync').status_code == 401
    # unknown gateway / no headers
    ghost = CloudClient(URL, ag.key, 'gw_ghost')
    assert _raw(app, ag, headers=ghost.sign_headers('POST', '/wifi/gateway/heartbeat', b'{}')).status_code == 401
    assert app.test_client().post('/wifi/gateway/heartbeat', json={}).status_code == 401


def test_failed_auth_does_not_consume_nonces_and_old_ones_purge(app, vend, tmp_path):
    ag, _ = _agent(app, tmp_path, vend[0])
    evil = CloudClient(URL, Ed25519PrivateKey.generate(), ag.client.gateway_uid)
    for _i in range(5):
        _raw(app, ag, headers=evil.sign_headers('POST', '/wifi/gateway/heartbeat', b'{}'))
    with app.app_context():
        assert WifiGatewayNonce.query.count() == 0           # strangers cannot fill the table
    assert _raw(app, ag).status_code == 200
    with app.app_context():
        WifiGatewayNonce.query.update({'created_at': vs.utcnow() - timedelta(days=2)})
        db.session.commit()
        assert gs.purge_old_nonces() == 1


# ------------------------- offline queue + idempotent sync ------------------
def test_offline_events_queue_then_sync_in_order_with_nothing_lost(app, vend, tmp_path):
    ag, tr = _agent(app, tmp_path, vend[0])
    tr.offline = True
    ids = [ag.record_event('session.started', {'n': i}) for i in range(5)]
    r = ag.run_once()
    assert r['online'] is False and r['pending'] == 5          # no exception, data kept
    tr.offline = False
    r = ag.run_once()
    assert r['synced'] == 5 and r['pending'] == 0
    with app.app_context():
        rows = WifiOfflineEvent.query.order_by(WifiOfflineEvent.seq).all()
        assert [x.event_id for x in rows] == ids and all(x.vendor_id == vend[1] for x in rows)


def test_crash_after_cloud_commit_resends_without_duplicates(app, vend, tmp_path):
    ag, _ = _agent(app, tmp_path, vend[0])
    for i in range(4):
        ag.record_event('usage.recorded', {'bytes': i})
    real_mark = ag.store.mark
    calls = {'n': 0}

    def crashing_mark(*a, **k):
        calls['n'] += 1
        if calls['n'] == 1:
            raise RuntimeError('power loss')
        return real_mark(*a, **k)
    ag.store.mark = crashing_mark
    with pytest.raises(RuntimeError):
        ag.run_once()
    assert ag.store.count() == 4                                 # agent thinks nothing was sent
    with app.app_context():
        assert WifiOfflineEvent.query.count() == 4               # but the cloud has them
    assert ag.run_once()['synced'] == 4 and ag.store.count() == 0
    with app.app_context():
        assert WifiOfflineEvent.query.count() == 4               # still 4: no duplicates
        from app.wifi.models import WifiSyncLog
        assert sum(x.duplicates for x in WifiSyncLog.query) == 4


def test_queue_is_durable_across_restart(tmp_path):
    p = str(tmp_path / 'q.db')
    s = Store(p)
    a, b = s.enqueue('gateway.event', {'x': 1}), s.enqueue('gateway.event', {'x': 2})
    s.db.close()
    s2 = Store(p)
    assert [e['event_id'] for e in s2.pending()] == [a, b]
    s2.mark([a], 'synced')
    s2.purge_synced(keep=0)
    assert [e['event_id'] for e in s2.pending()] == [b]          # purge never drops pending


def test_invalid_events_are_rejected_once_not_retried_forever(app, vend, tmp_path):
    ag, _ = _agent(app, tmp_path, vend[0])
    ag.record_event('totally.unknown', {'a': 1})
    ag.record_event('payment.pending', {'amount': 1000})
    r = ag.run_once()
    assert r['synced'] == 1 and r['rejected'] == 1 and r['pending'] == 0
    assert ag.status()['rejected_events'] == 1
    with app.app_context():
        assert [e.event_type for e in WifiOfflineEvent.query] == ['payment.pending']


def test_limits_on_batch_event_and_body_size(app, vend, tmp_path):
    ag, _ = _agent(app, tmp_path, vend[0])
    import json
    evs = [{'event_id': str(uuid.uuid4()), 'seq': i, 'type': 'gateway.event', 'payload': {}}
           for i in range(201)]
    body = json.dumps({'events': evs}).encode()
    assert _raw(app, ag, body, path='/wifi/gateway/sync').status_code == 400
    big = [{'event_id': str(uuid.uuid4()), 'seq': 0, 'type': 'gateway.event',
            'payload': {'blob': 'x' * 20000}}]
    r = _raw(app, ag, json.dumps({'events': big}).encode(), path='/wifi/gateway/sync')
    assert r.status_code == 200 and r.json['rejected'][0]['reason'] == 'payload too large'
    huge = b'{"events":[],"pad":"' + b'x' * (300 * 1024) + b'"}'
    assert _raw(app, ag, huge, path='/wifi/gateway/sync').status_code == 413


# ----------------------------- isolation + lifecycle ------------------------
def test_tenant_comes_from_the_gateway_key_never_from_the_payload(app, tmp_path):
    with app.app_context():
        (ua, va), (ub, vb) = _vendor_user(), _vendor_user()
    ga, _ = _agent(app, tmp_path, ua, 'GW A', 'a')
    gb, _ = _agent(app, tmp_path, ub, 'GW B', 'b')
    ga.record_event('gateway.event', {'vendor_id': vb, 'claim': 'I am vendor B'})
    ga.run_once()
    gb.run_once()
    with app.app_context():
        ev = WifiOfflineEvent.query.one()
        assert ev.vendor_id == va                                # not vb
    la = _login(app, ua).get('/wifi/vendor/gateways').json['gateways']
    lb = _login(app, ub).get('/wifi/vendor/gateways').json['gateways']
    assert [g['name'] for g in la] == ['GW A'] and [g['name'] for g in lb] == ['GW B']
    gid_a = la[0]['id']
    assert _login(app, ub).post(f'/wifi/vendor/gateways/{gid_a}/revoke').status_code == 404
    assert gb.run_once()['authorized'] is True and ga.run_once()['authorized'] is True


def test_revoked_and_suspended_gateways_are_locked_out(app, vend, tmp_path):
    uid, vid = vend
    ag, _ = _agent(app, tmp_path, uid)
    gid = _login(app, uid).get('/wifi/vendor/gateways').json['gateways'][0]['id']
    with app.app_context():
        admin = User(whatsapp='+5094' + str(uuid.uuid4().int)[:7], pseudo='a' + uuid.uuid4().hex[:8],
                     name='A', is_active=True, is_admin=True)
        admin.set_password('StrongPass123!')
        db.session.add(admin)
        db.session.commit()
        aid = admin.id
    adm = _login(app, aid)
    assert adm.post(f'/wifi/admin/gateways/{gid}/suspend').status_code == 200
    ag.record_event('gateway.event', {})
    r = ag.run_once()
    assert r['authorized'] is False and ag.status()['revoked'] is True
    with app.app_context():
        assert WifiOfflineEvent.query.count() == 0               # nothing accepted while suspended
    assert adm.post(f'/wifi/admin/gateways/{gid}/reactivate').status_code == 200
    assert ag.run_once()['synced'] == 1 and ag.status()['revoked'] is False
    assert _login(app, uid).post(f'/wifi/vendor/gateways/{gid}/revoke').status_code == 200
    assert ag.run_once()['authorized'] is False
    assert adm.post(f'/wifi/admin/gateways/{gid}/reactivate').status_code == 409   # final
    assert _login(app, uid).get('/wifi/admin/gateways').status_code in (302, 401, 403)


def test_suspended_vendor_gateway_keeps_syncing_but_is_told_to_stop_selling(app, vend, tmp_path):
    uid, vid = vend
    ag, _ = _agent(app, tmp_path, uid)
    with app.app_context():
        vs.suspend_vendor(db.session.get(WifiVendor, vid), 'abuse')
        db.session.commit()
    ag.record_event('session.ended', {'k': 1})
    r = ag.run_once()
    assert r['authorized'] and r['synced'] == 1                  # data is never dropped
    assert r['access']['state'] == 'SUSPENDED' and r['access']['can_sell'] is False
    assert r['access']['existing_entitlements_protected'] is True


def test_agent_refuses_plain_http_cloud_url():
    t = UrllibTransport()
    with pytest.raises(CloudRejected):
        t.request('POST', 'http://cloud.test/x', {}, b'{}')
