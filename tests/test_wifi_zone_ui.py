"""The Wi-Fi zone pages + the 'Sèvis' menu entry."""
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
from app.services.gkach_service import GkachService
from app.wifi import ui as wui
from app.wifi import vendor_service as vs
from app.wifi.models import WifiGateway, WifiTrial, WifiVendor
from app.wifi.policy import set_policy
from test_wifi_gateway import _login
from test_wifi_offline_e2e import MAC1, World
from test_wifi_purchases import PORTAL, _buyer, buy
from test_wifi_vouchers import _gen, _pkg


@pytest.fixture()
def app():
    a = create_app('testing')
    a.config['WTF_CSRF_ENABLED'] = False
    yield a
    with a.app_context():
        db.session.remove()
        db.drop_all()


def _user(app, admin=False, balance=0):
    with app.app_context():
        wa = '+5094' + str(uuid.uuid4().int)[:7]
        u = User(whatsapp=wa, pseudo='z' + uuid.uuid4().hex[:10], name='Z', auth_provider='whatsapp',
                 is_active=True, is_admin=admin)
        u.set_password('Str0ng-Passw0rd!')
        db.session.add(u)
        db.session.commit()
        if balance:
            GkachService.add_balance(wa, balance)
        return u.id, wa


def page(app, uid=None, **kw):
    c = _login(app, uid) if uid else app.test_client()
    r = c.get('/wifi/zone', **kw)
    assert r.status_code == 200
    return r.data.decode()


def text(html):                                           # visible text only, for readable assertions
    return re.sub(r'\s+', ' ', re.sub(r'<style.*?</style>|<[^>]+>', ' ', html, flags=re.S))


# ============================ menu + anonymous ==============================
def test_wifi_zone_is_listed_in_the_sevis_menu_on_every_page(app):
    for path in ('/', '/wifi/zone'):
        html = app.test_client().get(path).data.decode()
        assert 'href="/wifi/zone"' in html and 'Wi-Fi Zone' in html and 'Rezo Entènèt' in html, path
    assert html.count('Sèvis') >= 1


def test_anonymous_visitors_see_the_offer_and_a_login_link_but_no_data(app):
    World(app, __import__('pathlib').Path(__import__('tempfile').mkdtemp()))         # real data exists
    html = page(app)
    t = text(html)
    assert '3 jou gratis' in t and '1000 GKach' in t
    assert '/auth/login' in html and 'next=/wifi/zone' in html.replace('%2F', '/')
    for private in ('Main GW', 'Balans', 'Voucher Shop', 'Pòtay (gateways)'):
        assert private not in html


def test_the_offer_text_follows_the_admin_policy(app):
    with app.app_context():
        set_policy('trial_days', 5)
        set_policy('subscription_price_gkach', 1500)
        db.session.commit()
    t = text(page(app))
    assert '5 jou gratis' in t and '1500 GKach' in t


# ============================ becoming a vendor =============================
def test_signed_in_visitor_can_register_and_gets_the_free_trial(app):
    uid, wa = _user(app)
    c = _login(app, uid)
    html = c.get('/wifi/zone').data.decode()
    assert 'name="business_name"' in html and 'name="csrf_token"' in html and 'Vin yon vandè' in html
    r = c.post('/wifi/zone/register', data={'business_name': 'Cyber Mapou'}, follow_redirects=True)
    t = text(r.data.decode())
    assert 'Kont vandè ou kreye' in t and 'ESSAI' in t and '3 jou' in t and 'Vin yon vandè' not in t
    with app.app_context():
        v = WifiVendor.query.filter_by(user_id=uid).one()
        assert v.business_name == 'Cyber Mapou' and WifiTrial.query.filter_by(vendor_id=v.id).count() == 1


@pytest.mark.parametrize('name', ['x', '', '   ', 'a' * 121])
def test_registration_errors_are_shown_and_create_nothing(app, name):
    uid, _ = _user(app)
    r = _login(app, uid).post('/wifi/zone/register', data={'business_name': name}, follow_redirects=True)
    assert 'Business name' in r.data.decode()
    with app.app_context():
        assert WifiVendor.query.count() == 0


def test_registering_twice_is_refused_and_anonymous_cannot_register(app):
    uid, _ = _user(app)
    c = _login(app, uid)
    c.post('/wifi/zone/register', data={'business_name': 'First Shop'})
    r = c.post('/wifi/zone/register', data={'business_name': 'Second Shop'}, follow_redirects=True)
    assert 'already exists' in r.data.decode()
    anon = app.test_client().post('/wifi/zone/register', data={'business_name': 'Ghost'})
    assert anon.status_code == 302 and '/auth/login' in anon.headers['Location']
    with app.app_context():
        assert WifiVendor.query.count() == 1


# ============================== vendor dashboard ============================
@pytest.fixture()
def shop(app, tmp_path):
    w = World(app, tmp_path)
    w.agent.portal_url = PORTAL
    w.paid, w.gw_uid = w.pid, None
    assert w.agent.run_once()['authorized']
    w.gw_uid = w.agent.store.get('gateway_uid')
    return w


def test_vendor_dashboard_shows_status_gateways_packages_and_counts(app, shop):
    _gen(app, shop.uid, shop.pid, shop.gid, count=3)
    t = text(page(app, shop.uid))
    assert 'ESSAI' in t and '3 jou' in t and 'Pwochen faktirasyon' in t
    assert 'Main' in t and 'ONLINE' in t                                    # the enrolled, just-seen gateway
    assert '1 Hour' in t and '50 Gkach' in t and '60 minit' in t
    assert re.search(r'Vouchè\s+3\s+disponib · 0 itilize', t)
    assert 'Routè' in t and 'Peman kliyan yo' in t and '1000 GKach / 30 jou' in t


def test_gateway_chip_turns_offline_when_not_seen_and_shows_revocation(app, shop):
    with app.app_context():
        WifiGateway.query.update({'last_seen_at': vs.utcnow() - timedelta(minutes=6)})
        db.session.commit()
    t = text(page(app, shop.uid))
    assert 'OFFLINE' in t and 'vu 6 minit' in t
    _login(app, shop.uid).post(f'/wifi/vendor/gateways/{shop.gid}/revoke')
    assert 'REVOKED' in text(page(app, shop.uid))


def test_gateway_status_and_relative_time_helpers():
    now = vs.utcnow()
    mk = lambda **kw: type('G', (), dict({'status': 'ENROLLED', 'last_seen_at': None}, **kw))
    assert wui.gateway_status(mk(last_seen_at=now - timedelta(minutes=4)), now) == 'ONLINE'
    assert wui.gateway_status(mk(last_seen_at=now - timedelta(minutes=5, seconds=1)), now) == 'OFFLINE'
    assert wui.gateway_status(mk(), now) == 'OFFLINE'
    assert wui.gateway_status(mk(status='SUSPENDED', last_seen_at=now), now) == 'SUSPENDED'
    assert [wui.ago(None), wui.ago(now, now), wui.ago(now - timedelta(minutes=7), now),
            wui.ago(now - timedelta(hours=3), now), wui.ago(now - timedelta(days=2), now)] == [
        'jamè', 'kounye a', '7 minit', '3 èdtan', '2 jou']


def test_subscription_states_are_shown_with_clear_chips(app, shop):
    with app.app_context():
        vs.suspend_vendor(db.session.get(WifiVendor, shop.vid), 'abuse')
        db.session.commit()
    assert 'SUSPENDU' in text(page(app, shop.uid))
    with app.app_context():
        v = db.session.get(WifiVendor, shop.vid)
        vs.activate_vendor(v)
        set_policy('offline_grace_days', 0)
        WifiTrial.query.filter_by(vendor_id=shop.vid).update({'expires_at': vs.utcnow() - timedelta(days=1)})
        db.session.commit()
    t = text(page(app, shop.uid))
    assert 'EXPIRÉ' in t and 'Nouvo vant yo sispann' in t


def test_dashboard_has_helpful_empty_states(app, tmp_path):
    uid, _ = _user(app)
    _login(app, uid).post('/wifi/zone/register', data={'business_name': 'Empty Shop'})
    t = text(page(app, uid))
    assert 'Pa gen pòtay ankò' in t and 'Pa gen fòfè ankò' in t and 'poko achte okenn' in t


def test_customer_purchases_and_vendor_payment_totals(app, shop):
    bid, bwa = _buyer(app, 500)
    assert buy(app, bid, shop).status_code == 201
    mine = text(page(app, bid))
    assert 'Achte Wi-Fi mwen yo' in mine and '1 Hour' in mine and '50 Gkach' in mine and 'HELD' in mine
    assert 'Vin yon vandè' in mine                                           # buyer is not a vendor
    vendor = text(page(app, shop.uid))
    assert re.search(r'An atant livrezon\s+50 Gkach', vendor)
    other_id, _ = _user(app)
    assert '1 Hour' not in text(page(app, other_id))                          # other users do not see it


# ============================ privacy / safety ==============================
def test_no_secret_ever_reaches_the_html(app, shop):
    codes = _gen(app, shop.uid, shop.pid, shop.gid, count=3).json['codes']
    bid, _ = _buyer(app, 500)
    ticket = buy(app, bid, shop).json['purchase']['ticket']
    secrets_ = list(codes) + [c.replace('-', '') for c in codes] + [ticket, ticket.split('.')[0]]
    secrets_ += [shop.agent.store.get('voucher_key'), shop.agent.store.get('cloud_public_key')]
    with app.app_context():
        from app.wifi.models import WifiVoucher
        secrets_ += [v.code_hash for v in WifiVoucher.query]
    for uid in (shop.uid, bid):
        html = page(app, uid)
        for s in secrets_:
            assert s and s not in html


def test_vendor_controlled_text_is_escaped(app, shop):
    _login(app, shop.uid).post('/wifi/vendor/packages', json={
        'name': '<script>alert(1)</script>', 'duration_minutes': 30, 'price_gkach': 5})
    with app.app_context():
        WifiGateway.query.update({'name': '<img src=x onerror=alert(1)>'})
        db.session.commit()
    html = page(app, shop.uid)
    assert '<script>alert(1)' not in html and '<img src=x' not in html
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in html and '&lt;img src=x' in html


def test_vendors_never_see_each_others_data(app, shop, tmp_path):
    other = World(app, tmp_path / 'w2')
    _pkg(app, other.uid, name='SecretPlan-B', price_gkach=77)
    _gen(app, other.uid, other.pid, other.gid, count=2)
    mine = text(page(app, shop.uid))
    assert 'SecretPlan-B' not in mine and '77 Gkach' not in mine
    assert re.search(r'Vouchè\s+0\s+disponib', mine)
    theirs = text(page(app, other.uid))
    assert 'SecretPlan-B' in theirs and re.search(r'Vouchè\s+2\s+disponib', theirs)


def test_only_admins_see_the_network_summary(app, shop):
    aid, _ = _user(app, admin=True)
    t = text(page(app, aid))
    assert 'Admin — rezo a' in t and re.search(r'Vandè\s+1 \(1 aktif', t) and re.search(r'Pòtay\s+1 online / 1', t)
    assert 'Admin — rezo a' not in text(page(app, shop.uid))
    assert 'Admin — rezo a' not in text(page(app))


# ================================ renewal ===================================
def _renew(app, uid, key):
    return _login(app, uid).post('/wifi/zone/renew', data={'key': key}, follow_redirects=True)


def test_renewal_charges_once_even_if_the_form_is_submitted_twice(app, shop):
    with app.app_context():
        wa = db.session.get(WifiVendor, shop.vid).user.whatsapp
        GkachService.add_balance(wa, 1500)
    html = page(app, shop.uid)
    key = re.search(r'name="key" value="([0-9a-f]{32})"', html).group(1)
    r1 = _renew(app, shop.uid, key)
    assert 'Abònman renouvle: 1000 GKach' in r1.data.decode()
    r2 = _renew(app, shop.uid, key)                                           # double click / retry
    assert 'Abònman renouvle' in r2.data.decode()
    with app.app_context():
        assert GkachService.get_balance(wa) == 500                             # charged exactly once
    assert re.search(r'Balans GKach\s+500', text(r2.data.decode()))


def test_renewal_problems_are_explained_and_charge_nothing(app, shop):
    with app.app_context():
        wa = db.session.get(WifiVendor, shop.vid).user.whatsapp
        GkachService.add_balance(wa, 10)
    r = _renew(app, shop.uid, uuid.uuid4().hex)
    assert 'pa sifi' in r.data.decode()                                        # insufficient GKach
    assert 'abònman renouvle' not in r.data.decode().lower()
    with app.app_context():
        assert GkachService.get_balance(wa) == 10
    nv, _ = _user(app, balance=2000)
    assert 'poko vandè' in _renew(app, nv, uuid.uuid4().hex).data.decode()     # not a vendor
    anon = app.test_client().post('/wifi/zone/renew', data={'key': 'abcdefgh1234'})
    assert anon.status_code == 302 and '/auth/login' in anon.headers['Location']
    assert 'Idempotency' in _renew(app, shop.uid, 'short').data.decode()       # malformed key refused
