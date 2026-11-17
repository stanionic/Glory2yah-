"""Phase 7: GKach purchases, signed tickets, escrow settlement/refund, data quotas."""
import base64
import json
import os
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
from app.models.gkach_transaction import GkachTransaction
from app.models.user import User
from app.services.gkach_service import GkachService
from app.wifi import purchase_service as psv
from app.wifi import vendor_service as vs
from app.wifi.models import (WifiAuditLog, WifiGateway, WifiPurchase, WifiTrial, WifiUsageRecord,
                             WifiVendor)
from app.wifi.policy import set_policy
from gateway_agent.portal import engine as E
from gateway_agent.portal.access import NdsctlUsage
from test_wifi_gateway import _login
from test_wifi_offline_e2e import IP1, IP2, IP3, MAC1, MAC2, MAC3, World
from test_wifi_portal import call
from test_wifi_vouchers import _pkg

PORTAL = 'http://192.168.1.1:8080'


@pytest.fixture()
def app():
    a = create_app('testing')
    a.config['WTF_CSRF_ENABLED'] = False
    yield a
    with a.app_context():
        db.session.remove()
        db.drop_all()


def _buyer(app, balance=1000):
    with app.app_context():
        wa = '+5094' + str(uuid.uuid4().int)[:7]
        u = User(whatsapp=wa, pseudo='b' + uuid.uuid4().hex[:10], name='B', auth_provider='whatsapp',
                 is_active=True)
        u.set_password('Str0ng-Passw0rd!')
        db.session.add(u)
        db.session.commit()
        if balance:
            GkachService.add_balance(wa, balance)
        return u.id, wa


def bal(app, wa):
    with app.app_context():
        return GkachService.get_balance(wa)


@pytest.fixture()
def shop(app, tmp_path):
    w = World(app, tmp_path)
    w.agent.portal_url = PORTAL
    w.paid = w.pid                                              # World's '1 Hour' / 50 GKach / 60 min package
    w.quota = _pkg(app, w.uid, name='Data 1MB', price_gkach=30, duration_minutes=120, data_mb=1)
    assert w.agent.run_once()['authorized']                    # registers portal URL + syncs policy
    w.gw_uid = w.agent.store.get('gateway_uid')
    with app.app_context():
        w.vendor_wa = db.session.get(WifiVendor, w.vid).user.whatsapp
    return w


def buy(app, buyer_id, shop, pkg=None, mac=MAC1, key=None, **over):
    body = {'gateway_uid': shop.gw_uid, 'package_id': pkg or shop.paid,
            'device_tag': shop.agent.engine.tag_for(mac)}
    body.update(over)
    return _login(app, buyer_id).post('/wifi/customer/purchase', json=body,
                                      headers={'Idempotency-Key': key or uuid.uuid4().hex})


def send_ticket(shop, ticket, ip=IP1):
    return call(shop.portal, 'POST', '/ticket', 'ticket=' + ticket, ip=ip)


# ============================ portal URL registration ========================
@pytest.mark.parametrize('url', ['http://192.168.1.1:8080', 'https://wifi.lan', 'http://localhost:8080',
                                 'http://10.0.0.1', 'http://172.16.5.4:9000/', 'http://gw.local'])
def test_lan_portal_urls_are_accepted(url):
    assert psv.validate_portal_url(url).startswith(('http://', 'https://'))


@pytest.mark.parametrize('url', ['http://evil.com', 'https://8.8.8.8', 'ftp://192.168.1.1', '',
                                 'http://user:pw@192.168.1.1', 'http://192.168.1.1/admin',
                                 'http://192.168.1.1?x=1', 'javascript:alert(1)', 'http://192.168.1.1:99999',
                                 'http://192.168.1.1#frag', 'http://evil.com.lan.evil.com', None])
def test_public_or_odd_portal_urls_are_rejected(url):
    with pytest.raises(psv.PurchaseError):
        psv.validate_portal_url(url)


def test_gateway_registers_its_portal_url_via_signed_heartbeat(app, shop):
    with app.app_context():
        assert WifiGateway.query.one().portal_url == PORTAL
    shop.agent.portal_url = 'http://evil.example.com'              # a public URL is ignored
    shop.agent.run_once()
    with app.app_context():
        assert WifiGateway.query.one().portal_url == PORTAL


# ================================ purchase ===================================
def test_purchase_debits_holds_and_issues_a_verifiable_ticket(app, shop):
    bid, bwa = _buyer(app, 1000)
    r = buy(app, bid, shop)
    assert r.status_code == 201 and r.headers['Cache-Control'] == 'no-store'
    assert r.json['deliver_to'] == PORTAL + '/ticket' and r.json['replayed'] is False
    pur = r.json['purchase']
    assert pur['status'] == 'HELD' and pur['amount_gkach'] == 50
    assert bal(app, bwa) == 950 and bal(app, shop.vendor_wa) == 0       # held, vendor NOT paid yet
    with app.app_context():
        led = GkachTransaction.query.filter_by(user_whatsapp=bwa, transaction_type='wifi_purchase_hold').one()
        assert led.amount == 50 and led.transaction_id == WifiPurchase.query.one().ledger_transaction_id
    # the gateway can verify it offline with the cloud public key
    payload = shop.agent.engine._verify_ticket(pur['ticket'], shop.agent.store.get('cloud_public_key'))
    assert payload['gw'] == shop.gw_uid and payload['tid'] == pur['ticket_id']
    assert payload['dt'] == shop.agent.engine.tag_for(MAC1)
    assert payload['pk'] == {'n': '1 Hour', 'dur': 60, 'mb': None, 'dn': 2000, 'up': 1000, 'md': 2}


def test_same_idempotency_key_returns_the_same_ticket_and_charges_once(app, shop):
    bid, bwa = _buyer(app, 1000)
    r1, r2 = buy(app, bid, shop, key='purchase-key-001'), buy(app, bid, shop, key='purchase-key-001')
    assert (r1.status_code, r2.status_code) == (201, 200) and r2.json['replayed'] is True
    assert r1.json['purchase']['ticket'] == r2.json['purchase']['ticket']
    assert bal(app, bwa) == 950
    with app.app_context():
        assert WifiPurchase.query.count() == 1
    assert buy(app, bid, shop, key='purchase-key-001', pkg=shop.quota).status_code == 409   # other purchase
    assert buy(app, bid, shop, key='purchase-key-001', mac=MAC2).status_code == 409
    assert bal(app, bwa) == 950


def test_idempotency_keys_are_per_buyer(app, shop):
    (b1, w1), (b2, w2) = _buyer(app, 500), _buyer(app, 500)
    assert buy(app, b1, shop, key='shared-key-0001').status_code == 201
    assert buy(app, b2, shop, key='shared-key-0001').status_code == 201      # not a replay of b1's
    assert (bal(app, w1), bal(app, w2)) == (450, 450)


def test_insufficient_funds_changes_nothing(app, shop):
    bid, bwa = _buyer(app, 49)
    r = buy(app, bid, shop)
    assert r.status_code == 402 and bal(app, bwa) == 49
    with app.app_context():
        assert WifiPurchase.query.count() == 0


@pytest.mark.parametrize('over,status', [
    ({'package_id': 99999}, 404), ({'package_id': 'x'}, 404), ({'package_id': True}, 404),
    ({'gateway_uid': 'gw_nope'}, 404), ({'device_tag': 'short'}, 400), ({'device_tag': 'Z' * 32}, 400)])
def test_purchase_input_validation(app, shop, over, status):
    bid, bwa = _buyer(app, 500)
    assert buy(app, bid, shop, **over).status_code == status
    assert bal(app, bwa) == 500


def test_bad_idempotency_keys_and_anonymous_access(app, shop):
    bid, bwa = _buyer(app, 500)
    assert buy(app, bid, shop, key='short').status_code == 400
    assert app.test_client().post('/wifi/customer/purchase', json={}).status_code == 401
    assert bal(app, bwa) == 500


def test_cannot_buy_inactive_or_free_packages_or_from_your_own_network(app, shop):
    bid, bwa = _buyer(app, 500)
    vendor = _login(app, shop.uid)
    free = vendor.post('/wifi/vendor/packages', json={'name': 'Free', 'duration_minutes': 15,
                                                      'price_gkach': 0}).json['id']
    assert buy(app, bid, shop, pkg=free).status_code == 404
    vendor.patch(f'/wifi/vendor/packages/{shop.paid}', json={'is_active': False})
    assert buy(app, bid, shop).status_code == 404
    assert buy(app, shop.uid, shop, pkg=shop.quota).status_code == 400      # the vendor themself
    assert bal(app, bwa) == 500


def test_package_of_another_vendor_cannot_be_bought_through_this_gateway(app, shop, tmp_path):
    other = World(app, tmp_path / 'w2')
    other_pkg = _pkg(app, other.uid, name='Theirs', price_gkach=10)
    bid, bwa = _buyer(app, 500)
    assert buy(app, bid, shop, pkg=other_pkg).status_code == 404
    assert bal(app, bwa) == 500


def test_no_sales_when_the_vendors_subscription_lapsed_or_gateway_unusable(app, shop):
    bid, bwa = _buyer(app, 500)
    _login(app, shop.uid).post(f'/wifi/vendor/gateways/{shop.gid}/revoke')
    assert buy(app, bid, shop).status_code == 404
    assert bal(app, bwa) == 500


def test_expired_subscription_blocks_new_purchases(app, shop):
    bid, bwa = _buyer(app, 500)
    with app.app_context():
        set_policy('offline_grace_days', 0)
        WifiTrial.query.filter_by(vendor_id=shop.vid).update({'expires_at': vs.utcnow() - timedelta(days=1)})
        db.session.commit()
    assert buy(app, bid, shop).status_code == 503 and bal(app, bwa) == 500


def test_gateway_without_registered_portal_cannot_sell(app, shop):
    bid, bwa = _buyer(app, 500)
    with app.app_context():
        WifiGateway.query.update({'portal_url': None})
        db.session.commit()
    assert buy(app, bid, shop).status_code == 409 and bal(app, bwa) == 500


# ============================ delivery + settlement ==========================
def test_pay_ticket_redeem_settle_full_cycle_conserves_gkach(app, shop):
    bid, bwa = _buyer(app, 1000)
    start = bal(app, bwa) + bal(app, shop.vendor_wa)
    ticket = buy(app, bid, shop).json['purchase']['ticket']
    s, _, body = send_ticket(shop, ticket)                                       # customer's browser -> gateway
    assert s == 200 and 'Ou konekte' in body
    verb, mac, ip, grant = shop.access.calls[-1]
    assert (verb, mac, ip) == ('authorize', MAC1, IP1)
    assert (grant['package'], grant['seconds_remaining'], grant['down_kbps'], grant['source']) == (
        '1 Hour', 3600, 2000, 'purchase')
    assert bal(app, shop.vendor_wa) == 0                                         # still held: not synced yet
    assert shop.agent.run_once()['synced'] == 1
    assert bal(app, shop.vendor_wa) == 50 and bal(app, bwa) == 950               # released to the vendor
    assert bal(app, bwa) + bal(app, shop.vendor_wa) == start
    pay = _login(app, shop.uid).get('/wifi/vendor/payments').json
    assert pay['totals_gkach'] == {'HELD': 0, 'SETTLED': 50, 'REFUNDED': 0, 'CONFLICT': 0}
    with app.app_context():
        assert WifiPurchase.query.one().status == 'SETTLED'
        assert GkachTransaction.query.filter_by(user_whatsapp=shop.vendor_wa, transaction_type='wifi_sale').count() == 1


def test_replayed_redemption_events_pay_the_vendor_once(app, shop):
    bid, bwa = _buyer(app, 1000)
    ticket = buy(app, bid, shop).json['purchase']['ticket']
    send_ticket(shop, ticket)
    ev = shop.agent.store.pending()[0]
    body = json.dumps({'events': [ev]}).encode()
    for _ in range(3):
        h = shop.agent.client.sign_headers('POST', '/wifi/gateway/sync', body)
        assert app.test_client().post('/wifi/gateway/sync', data=body, headers=h).status_code == 200
    forged = dict(ev, event_id=str(uuid.uuid4()))                               # same ticket, NEW event id
    body = json.dumps({'events': [forged]}).encode()
    h = shop.agent.client.sign_headers('POST', '/wifi/gateway/sync', body)
    app.test_client().post('/wifi/gateway/sync', data=body, headers=h)
    assert bal(app, shop.vendor_wa) == 50                                        # paid exactly once


def test_another_gateway_cannot_settle_someone_elses_ticket(app, shop, tmp_path):
    bid, bwa = _buyer(app, 1000)
    ticket = buy(app, bid, shop).json['purchase']['ticket']
    tid = shop.agent.engine._verify_ticket(ticket, shop.agent.store.get('cloud_public_key'))['tid']
    thief = World(app, tmp_path / 'thief')
    thief.agent.run_once()
    thief.agent.record_event('ticket.redeemed', {'ticket_id': tid, 'device': MAC1,
                                                 'redeemed_at': '2026-11-13T10:00:00Z',
                                                 'ends_at': '2026-11-13T11:00:00Z'})
    thief.agent.run_once()
    assert bal(app, thief.vendor_wa if hasattr(thief, 'vendor_wa') else '+0') in (0,)
    with app.app_context():
        assert WifiPurchase.query.one().status == 'HELD'                         # untouched
        assert WifiAuditLog.query.filter_by(action='purchase.event_rejected').count() == 1
    assert bal(app, shop.vendor_wa) == 0


@pytest.mark.parametrize('payload', [{}, {'ticket_id': 'nope'}, {'ticket_id': 'tk_' + 'z' * 16},
                                     {'ticket_id': 123}, {'ticket_id': 'tk_0000000000000000'}])
def test_malformed_or_unknown_ticket_events_are_rejected_without_blocking_sync(app, shop, payload):
    shop.agent.record_event('ticket.redeemed', payload)
    shop.agent.record_event('gateway.event', {'still': 'processed'})
    r = shop.agent.run_once()
    assert r['synced'] == 2 and r['pending'] == 0
    assert bal(app, shop.vendor_wa) == 0


def test_unredeemed_purchases_are_refunded_after_expiry_plus_grace(app, shop):
    bid, bwa = _buyer(app, 1000)
    buy(app, bid, shop)
    assert bal(app, bwa) == 950
    with app.app_context():
        assert psv.refund_expired_purchases() == 0                               # not expired yet
        WifiPurchase.query.update({'ticket_expires_at': vs.utcnow() - timedelta(hours=10)})
        db.session.commit()
        assert psv.refund_expired_purchases() == 0                               # inside the 72h grace
        WifiPurchase.query.update({'ticket_expires_at': vs.utcnow() - timedelta(hours=80)})
        db.session.commit()
        assert psv.refund_expired_purchases() == 1
        assert psv.refund_expired_purchases() == 0                               # idempotent
    assert bal(app, bwa) == 1000 and bal(app, shop.vendor_wa) == 0
    with app.app_context():
        assert WifiPurchase.query.one().status == 'REFUNDED'
        assert GkachTransaction.query.filter_by(user_whatsapp=bwa, transaction_type='wifi_refund').count() == 1


def test_delivery_after_a_refund_is_flagged_and_the_vendor_is_not_paid_twice(app, shop):
    bid, bwa = _buyer(app, 1000)
    ticket = buy(app, bid, shop).json['purchase']['ticket']
    send_ticket(shop, ticket)                                                    # redeemed offline...
    with app.app_context():
        WifiPurchase.query.update({'ticket_expires_at': vs.utcnow() - timedelta(hours=100)})
        db.session.commit()
        psv.refund_expired_purchases()                                           # ...refund wins the race
    assert bal(app, bwa) == 1000
    shop.agent.run_once()                                                        # the late event arrives
    with app.app_context():
        assert WifiPurchase.query.one().status == 'CONFLICT'
        assert WifiAuditLog.query.filter_by(action='purchase.conflict').count() == 1
    assert bal(app, shop.vendor_wa) == 0 and bal(app, bwa) == 1000               # nobody paid twice


def test_refund_job_is_admin_only(app, shop):
    bid, _ = _buyer(app, 10)
    assert _login(app, bid).post('/wifi/admin/jobs/refund-expired-purchases').status_code in (302, 401, 403)
    with app.app_context():
        admin = User(whatsapp='+5094' + str(uuid.uuid4().int)[:7], pseudo='a' + uuid.uuid4().hex[:8], name='A',
                     is_active=True, is_admin=True)
        admin.set_password('Str0ng-Passw0rd!')
        db.session.add(admin)
        db.session.commit()
        aid = admin.id
    assert _login(app, aid).post('/wifi/admin/jobs/refund-expired-purchases').json == {'refunded': 0}


def test_history_views_are_private_and_never_leak_tickets(app, shop):
    (b1, w1), (b2, w2) = _buyer(app, 500), _buyer(app, 500)
    t1 = buy(app, b1, shop).json['purchase']['ticket']
    buy(app, b2, shop, pkg=shop.quota)
    mine = _login(app, b1).get('/wifi/customer/purchases').json['purchases']
    assert [p['package'] for p in mine] == ['1 Hour'] and 'ticket' not in mine[0]
    assert t1 not in json.dumps(_login(app, b2).get('/wifi/customer/purchases').json)
    pay = _login(app, shop.uid).get('/wifi/vendor/payments').json
    assert pay['totals_gkach']['HELD'] == 80 and len(pay['payments']) == 2
    assert t1 not in json.dumps(pay)
    other = World(app, shop.tmp / 'w3')
    assert _login(app, other.uid).get('/wifi/vendor/payments').json['payments'] == []
    assert app.test_client().get('/wifi/customer/purchases').status_code in (302, 401)


# ================================ buy page ===================================
def test_buy_page_shows_the_offer_then_pays_and_hands_the_ticket_to_the_gateway(app, shop):
    bid, bwa = _buyer(app, 500)
    c = _login(app, bid)
    tag = shop.agent.engine.tag_for(MAC1)
    page = c.get(f'/wifi/buy?gw={shop.gw_uid}&pkg={shop.paid}&d={tag}')
    html = page.data.decode()
    assert page.status_code == 200 and '1 Hour' in html and '50 Gkach' in html and '500 Gkach' in html
    assert page.headers['X-Frame-Options'] == 'DENY' and page.headers['Cache-Control'] == 'no-store'
    import re
    key = re.search(r'name="key" value="([0-9a-f]+)"', html).group(1)
    form = {'gw': shop.gw_uid, 'pkg': shop.paid, 'd': tag, 'key': key}
    r = c.post('/wifi/buy', data=form)
    assert r.status_code == 200 and f'action="{PORTAL}/ticket"' in r.data.decode()
    ticket = re.search(r'name="ticket" value="([^"]+)"', r.data.decode()).group(1)
    assert send_ticket(shop, ticket)[0] == 200
    assert c.post('/wifi/buy', data=form).status_code == 200                      # double submit
    assert bal(app, bwa) == 450                                                   # charged once


def test_buy_page_errors_are_friendly_and_safe(app, shop):
    bid, bwa = _buyer(app, 10)
    c = _login(app, bid)
    tag = shop.agent.engine.tag_for(MAC1)
    assert c.get(f'/wifi/buy?gw=gw_nope&pkg={shop.paid}&d={tag}').status_code == 404
    assert c.get(f'/wifi/buy?gw={shop.gw_uid}&pkg=abc&d={tag}').status_code == 404
    r = c.post('/wifi/buy', data={'gw': shop.gw_uid, 'pkg': shop.paid, 'd': tag, 'key': 'a' * 16})
    assert r.status_code == 402 and 'insuffisant' in r.data.decode().lower() or r.status_code == 402
    assert bal(app, bwa) == 10
    assert app.test_client().get(f'/wifi/buy?gw={shop.gw_uid}&pkg={shop.paid}&d={tag}').status_code in (302, 401)


# ============================ ticket security (gateway) ======================
def _ticket(app, shop, mac=MAC1, pkg=None):
    bid, _ = _buyer(app, 1000)
    return buy(app, bid, shop, pkg=pkg, mac=mac).json['purchase']['ticket']


def test_a_ticket_only_works_from_the_device_it_was_bought_for(app, shop):
    t = _ticket(app, shop, mac=MAC1)
    assert send_ticket(shop, t, ip=IP2)[0] == 400                                 # MAC2 tries MAC1's ticket
    assert shop.access.calls == []
    assert send_ticket(shop, t, ip=IP1)[0] == 200
    assert send_ticket(shop, t, ip=IP2)[0] == 400                                 # still not usable elsewhere
    assert [c[1] for c in shop.access.calls] == [MAC1]


def test_a_redeemed_ticket_reconnects_the_same_device_without_new_events(app, shop):
    t = _ticket(app, shop)
    send_ticket(shop, t)
    shop.offset = 600
    s, _, _ = send_ticket(shop, t)
    assert s == 200 and shop.access.calls[-1][3]['reconnect'] is True
    assert 2990 <= shop.access.calls[-1][3]['seconds_remaining'] <= 3000      # real clock + 600s offset
    assert len([e for e in shop.agent.store.pending() if e['type'] == 'ticket.redeemed']) == 1


def test_tickets_for_other_gateways_tampered_or_forged_tickets_are_refused(app, shop, tmp_path):
    t = _ticket(app, shop)
    body, sig = t.split('.')
    pad = lambda x: x + '=' * (-len(x) % 4)
    payload = json.loads(base64.urlsafe_b64decode(pad(body)))
    tamper = lambda p: base64.urlsafe_b64encode(json.dumps(p, separators=(',', ':'), sort_keys=True).encode()
                                                ).rstrip(b'=').decode() + '.' + sig
    longer = json.loads(json.dumps(payload))
    longer['pk']['dur'] = 99999
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    evil_body = body
    evil_sig = base64.urlsafe_b64encode(Ed25519PrivateKey.generate().sign(evil_body.encode())).rstrip(b'=').decode()
    cases = ['', 'garbage', 'a.b', t + 'x', body, sig, body + '.' + sig[:-4] + 'AAAA', tamper(longer),
             evil_body + '.' + evil_sig, t.replace('.', '..'), 'x' * 5000]
    for bad in cases:
        # Judge EVERY case on its own: without this, the 5-failure lockout turns all later
        # cases into 429 and would hide a broken signature check.
        shop.agent.engine.store.db.execute('DELETE FROM attempts')
        # sent from the device the ticket was bought for (IP1/MAC1): the device-tag check
        # would otherwise reject these first and hide a missing signature check
        s, _, _ = send_ticket(shop, bad, ip=IP1)
        assert s == (413 if len(bad) > 4000 else 400), (s, bad[:30])
    assert shop.access.calls == []                                        # not one was honoured
    shop.agent.engine.store.db.execute('DELETE FROM attempts')
    # A second gateway with the SAME cloud key and the SAME voucher key (so the device tag
    # matches too): only the ticket's gateway binding can stop it.
    other = World(app, tmp_path / 'g2')
    other.agent.run_once()
    other.agent.engine.store.set('cloud_public_key', shop.agent.store.get('cloud_public_key'))
    other.agent.engine.store.set('voucher_key', shop.agent.store.get('voucher_key'))
    assert other.agent.engine.tag_for(MAC1) == shop.agent.engine.tag_for(MAC1)
    assert call(other.portal, 'POST', '/ticket', 'ticket=' + t, ip=IP1)[0] == 400   # bound to ITS gateway
    assert other.access.calls == []
    assert send_ticket(shop, t)[0] == 200                                    # the intended gateway still accepts it


def test_an_expired_unredeemed_ticket_is_refused(app, shop):
    t = _ticket(app, shop)
    shop.offset = 31 * 60                                                          # ticket valid 30 min
    assert send_ticket(shop, t)[0] == 400 and shop.access.calls == []


def test_ticket_guessing_is_rate_limited_per_device(app, shop):
    t = _ticket(app, shop)
    for _ in range(5):
        send_ticket(shop, 'bogus.ticket')
    s, h, _ = send_ticket(shop, t)                                                 # the GOOD ticket, locked
    assert s == 429 and int(h['Retry-After']) > 0 and shop.access.calls == []


def test_tickets_redeem_with_the_cloud_unreachable(app, shop):
    t = _ticket(app, shop)
    shop.tr.offline = True
    assert send_ticket(shop, t)[0] == 200                                          # verified fully offline
    assert shop.agent.run_once()['online'] is False
    shop.tr.offline = False
    assert shop.agent.run_once()['synced'] == 1 and bal(app, shop.vendor_wa) == 50


def test_a_paid_customer_is_served_even_after_the_subscription_lapsed(app, shop):
    t = _ticket(app, shop)
    with app.app_context():
        set_policy('offline_grace_days', 0)
        WifiTrial.query.filter_by(vendor_id=shop.vid).update({'expires_at': vs.utcnow() - timedelta(days=1)})
        db.session.commit()
    assert shop.agent.run_once()['access']['can_sell'] is False
    assert send_ticket(shop, t)[0] == 200                                           # already paid: honoured


# ============================ usage and data quota ===========================
MB = 1024 * 1024


def _quota_session(app, shop):
    t = _ticket(app, shop, pkg=shop.quota)
    assert send_ticket(shop, t)[0] == 200
    return shop.agent.engine


def test_data_quota_cuts_access_when_used_up(app, shop):
    eng = _quota_session(app, shop)
    assert eng.record_usage({MAC1: (400 * 1024, 100 * 1024)}) == []                # 0.49 MB of 1 MB
    assert eng.status(MAC1)['seconds_remaining'] > 0
    assert eng.record_usage({MAC1: (700 * 1024, 150 * 1024)}) == []                # 0.83 MB: still under
    assert eng.record_usage({MAC1: (900 * 1024, 200 * 1024)}) == [MAC1]            # 1.07 MB >= 1 MB quota
    ended = [e for e in shop.agent.store.pending() if e['type'] == 'session.ended']
    assert ended and ended[-1]['payload']['reason'] == 'data_exhausted'
    assert eng.status(MAC1) is None                                                 # no longer active
    assert send_ticket(shop, 'x')[0] in (400, 429)


def test_usage_counter_resets_are_not_double_counted_and_unknown_devices_ignored(app, shop):
    eng = _quota_session(app, shop)
    eng.record_usage({MAC1: (100_000, 0)})
    eng.record_usage({MAC1: (150_000, 0)})                                          # +50k
    eng.record_usage({MAC1: (20_000, 0)})                                           # counter reset: +20k
    row = eng.store.db.execute('SELECT used_down FROM entitlements').fetchone()
    assert row[0] == 100_000 + 50_000 + 20_000
    assert eng.record_usage({MAC3: (10 * MB, 10 * MB), 'junk': (1, 1), MAC1: ('x', 1), MAC2: (-5, 0)}) == []
    assert eng.store.db.execute('SELECT used_down FROM entitlements').fetchone()[0] == 170_000


def test_maintain_enforces_quota_and_deauthorizes_the_device(app, shop):
    _quota_session(app, shop)

    class Usage:
        def read(self):
            return {MAC1: (2 * MB, 0)}
    gone = shop.agent.maintain(shop.access, Usage())
    assert gone == [MAC1] and ('deauthorize', MAC1) in shop.access.calls


def test_usage_reports_reach_the_cloud_once_and_are_validated(app, shop):
    eng = _quota_session(app, shop)
    eng.record_usage({MAC1: (300_000, 50_000)})
    assert eng.flush_usage() == 0                                                   # active: batched hourly
    assert eng.flush_usage(force=True) == 1
    assert eng.flush_usage(force=True) == 0                                         # nothing new
    eng.record_usage({MAC1: (500_000, 80_000)})
    eng.flush_usage(force=True)
    shop.agent.run_once()
    with app.app_context():
        recs = WifiUsageRecord.query.order_by(WifiUsageRecord.id).all()
        assert [(r.source, r.bytes_down, r.bytes_up) for r in recs] == [
            ('purchase', 300_000, 50_000), ('purchase', 200_000, 30_000)]
        assert all(r.ref.startswith('tk_') and r.vendor_id == shop.vid for r in recs)
    for bad in ({'source': 'x', 'ref': 'a', 'bytes_down': 1, 'bytes_up': 1},
                {'source': 'voucher', 'ref': '', 'bytes_down': 1, 'bytes_up': 1},
                {'source': 'voucher', 'ref': 'a', 'bytes_down': -1, 'bytes_up': 1},
                {'source': 'voucher', 'ref': 'a', 'bytes_down': True, 'bytes_up': 1},
                {'source': 'voucher', 'ref': 'a', 'bytes_down': 10 ** 14, 'bytes_up': 1}):
        shop.agent.record_event('usage.recorded', dict(bad, period_end='2026-11-13T10:00:00Z'))
    assert shop.agent.run_once()['pending'] == 0
    with app.app_context():
        assert WifiUsageRecord.query.count() == 2                                   # none of the bad ones


def test_ended_sessions_are_flushed_immediately(app, shop):
    eng = _quota_session(app, shop)
    eng.record_usage({MAC1: (200_000, 0)})
    shop.offset = 3 * 3600
    shop.agent.maintain(shop.access)                                                # expires + flushes
    assert [e['payload']['bytes_down'] for e in shop.agent.store.pending() if e['type'] == 'usage.recorded'] == [200_000]


def test_voucher_sessions_report_usage_with_their_voucher_uid(app, shop):
    from test_wifi_vouchers import _gen
    code = _gen(app, shop.uid, shop.paid, shop.gid, count=1).json['codes'][0]
    shop.agent.run_once()
    assert call(shop.portal, 'POST', '/redeem', 'code=' + code, ip=IP1)[0] == 200
    shop.agent.engine.record_usage({MAC1: (123, 45)})
    shop.agent.engine.flush_usage(force=True)
    shop.agent.run_once()
    with app.app_context():
        r = WifiUsageRecord.query.one()
        assert r.source == 'voucher' and r.ref.startswith('v_') and (r.bytes_down, r.bytes_up) == (123, 45)


def test_ndsctl_usage_parses_clients_and_survives_garbage():
    import types
    sample = json.dumps({'clients': {'1': {'mac': 'AA:BB:CC:00:00:01', 'downloaded': 10, 'uploaded': 5},
                                     '2': {'mac': 'bad', 'downloaded': 1, 'uploaded': 1},
                                     '3': {'mac': 'aa:bb:cc:00:00:03'}}})
    ok = types.SimpleNamespace(returncode=0, stdout=sample)
    assert NdsctlUsage(run=lambda *a, **k: ok).read() == {MAC1: (10 * 1024, 5 * 1024)}
    for out in (types.SimpleNamespace(returncode=1, stdout=''), types.SimpleNamespace(returncode=0, stdout='not json'),
                types.SimpleNamespace(returncode=0, stdout='[]')):
        assert NdsctlUsage(run=lambda *a, **k: out).read() == {}
    def boom(*a, **k):
        raise FileNotFoundError()
    assert NdsctlUsage(run=boom).read() == {}


# ================================ portal buy card ============================
def test_portal_shows_buy_links_with_the_opaque_device_tag_only_when_selling(app, shop):
    s, _, page = call(shop.portal, 'GET', '/', ip=IP1)
    tag = shop.agent.engine.tag_for(MAC1)
    assert s == 200 and 'Achte ak Gkach' in page
    assert f'gw={shop.gw_uid}' in page and f'd={tag}' in page and '1 Hour' in page
    assert MAC1 not in page and 'aa%3Abb' not in page                              # raw MAC never exposed
    assert 'Free' not in page.split('Achte ak Gkach')[1].split('</div>')[0]        # only paid packages
    assert call(shop.portal, 'GET', '/', ip='10.9.9.9')[2].count('Achte ak Gkach') == 0   # unknown device
    shop.offset = 3600                                                              # cloud not seen for an hour
    assert 'Achte ak Gkach' not in call(shop.portal, 'GET', '/')[2]


def test_portal_hides_buy_links_when_the_vendor_cannot_sell(app, shop):
    shop.agent.engine.store.set('access', {'can_sell': False, 'state': 'EXPIRED'})
    assert 'Achte ak Gkach' not in call(shop.portal, 'GET', '/')[2]


def test_portal_never_builds_buy_links_to_a_non_https_cloud(app, shop):
    shop.agent.engine.store.set('cloud_base_url', 'http://evil.example')
    assert 'Achte ak Gkach' not in call(shop.portal, 'GET', '/')[2]
    shop.agent.engine.store.set('cloud_base_url', 'javascript:alert(1)')
    assert 'javascript' not in call(shop.portal, 'GET', '/')[2]
