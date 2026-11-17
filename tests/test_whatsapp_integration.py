"""CallMeBot admin alerts + wa.me click-to-chat between visitors and ad owners/sellers.

A DUMMY key is used throughout: the real CallMeBot key must live only in the
CALLMEBOT_APIKEY environment variable (Render dashboard), never in the repo.
"""
import logging
import os
import sys
import uuid

import pytest

os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('SECRET_KEY', 'wa-tests-secret')
os.environ.setdefault('WTF_CSRF_ENABLED', 'False')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import create_app, db
from app.models.ad import Ad
from app.models.user import User
from app.services import notification_service as ns
from app.services.notification_service import NotificationService as NS

KEY = 'dummy-key-8675309'
PHONE = '50900000001'


class FakeResp:
    def __init__(self, text='Message queued to send.', status=200):
        self.text, self.status_code = text, status


@pytest.fixture()
def fake_http(monkeypatch):
    """Replace requests.get/post so no test ever touches the network."""
    import requests
    calls = []

    def get(url, **kw):
        calls.append(('GET', url))
        return FakeResp()
    monkeypatch.setattr(requests, 'get', get)
    monkeypatch.setattr(requests, 'post', lambda *a, **k: calls.append(('POST', a[0])) or FakeResp())
    for var in ('CALLMEBOT_APIKEY', 'ULTRAMSG_INSTANCE_ID', 'ULTRAMSG_TOKEN', 'WHATSAPP_CLOUD_TOKEN',
                'WHATSAPP_CLOUD_PHONE_ID', 'WHATSAPP_ALERT_WEBHOOK_URL'):
        monkeypatch.delenv(var, raising=False)
    return calls


# ------------------------------ CallMeBot (admin) ----------------------------
def test_admin_alert_goes_through_callmebot_with_the_env_key(fake_http, monkeypatch):
    monkeypatch.setenv('CALLMEBOT_APIKEY', KEY)
    assert ns._send_whatsapp_alert('Nouvo piblisite', phone=PHONE, allow_callmebot=True) == 'callmebot'
    method, url = fake_http[0]
    assert url.startswith('https://api.callmebot.com/whatsapp.php?')
    assert f'phone={PHONE}' in url and f'apikey={KEY}' in url and 'Nouvo%20piblisite' in url


def test_callmebot_is_admin_only_and_never_used_for_user_facing_sends(fake_http, monkeypatch):
    """Its key is bound to ONE number, so it must not carry OTPs or user messages."""
    monkeypatch.setenv('CALLMEBOT_APIKEY', KEY)
    assert ns._send_whatsapp_alert('123456', phone=PHONE, allow_callmebot=False) is None
    assert fake_http == []


def test_no_key_means_callmebot_is_skipped_quietly(fake_http):
    assert ns._send_whatsapp_alert('x', phone=PHONE, allow_callmebot=True) is None
    assert fake_http == []


def test_failed_send_never_writes_the_api_key_to_the_logs(fake_http, monkeypatch, caplog):
    import requests
    monkeypatch.setenv('CALLMEBOT_APIKEY', KEY)

    def boom(url, **kw):   # exactly what requests does: the URL (with key) is in the message
        raise requests.exceptions.ConnectionError(
            f"HTTPSConnectionPool(host='api.callmebot.com'): Max retries exceeded with url: "
            f"/whatsapp.php?phone={PHONE}&text=hi&apikey={KEY}")
    monkeypatch.setattr(requests, 'get', boom)
    caplog.set_level(logging.DEBUG)
    assert ns._send_whatsapp_alert('hi', phone=PHONE, allow_callmebot=True) is None
    assert KEY not in caplog.text
    assert 'apikey=***' in caplog.text


def test_rejected_response_echoing_the_key_is_redacted_in_logs(fake_http, monkeypatch, caplog):
    import requests
    monkeypatch.setenv('CALLMEBOT_APIKEY', KEY)
    monkeypatch.setattr(requests, 'get', lambda url, **k: FakeResp(f'ERROR: bad apikey={KEY}', 200))
    caplog.set_level(logging.DEBUG)
    ns._send_whatsapp_alert('hi', phone=PHONE, allow_callmebot=True)
    assert KEY not in caplog.text


def test_unacknowledged_callmebot_reply_is_redacted_in_logs(fake_http, monkeypatch, caplog):
    import requests
    monkeypatch.setenv('CALLMEBOT_APIKEY', KEY)
    monkeypatch.setattr(requests, 'get', lambda url, **k: FakeResp(f'APIKey is invalid: {KEY}', 200))
    caplog.set_level(logging.DEBUG)
    assert ns._send_whatsapp_alert('hi', phone=PHONE, allow_callmebot=True) is None
    assert KEY not in caplog.text and 'not acknowledged' in caplog.text


@pytest.mark.parametrize('text,expected_absent', [
    ('GET /x?apikey=abc12345&phone=1', 'abc12345'),
    ('url?token=sEcReT99&x=1', 'sEcReT99'),
    ('...&API_KEY=zzzz1111', 'zzzz1111'),
    ('access_token=EAAB12345 end', 'EAAB12345'),
])
def test_redact_secrets_masks_query_credentials(text, expected_absent):
    out = ns._redact_secrets(text)
    assert expected_absent not in out and '***' in out


def test_redact_secrets_masks_configured_values_anywhere(monkeypatch):
    monkeypatch.setenv('CALLMEBOT_APIKEY', KEY)
    assert KEY not in ns._redact_secrets(f'weird format: {KEY} inline')
    assert ns._redact_secrets('plain text') == 'plain text'


# ------------------------------- wa.me helper --------------------------------
@pytest.mark.parametrize('raw,expected', [
    ('+50942882076', 'https://wa.me/50942882076'),
    ('50942882076', 'https://wa.me/50942882076'),
    ('+509 4288-2076', 'https://wa.me/50942882076'),
    ('(509) 42.88.20.76', 'https://wa.me/50942882076'),
])
def test_wa_me_link_normalises_numbers(raw, expected):
    assert NS.generate_whatsapp_link(raw) == expected


@pytest.mark.parametrize('bad', [None, '', '+', 'abc', '123', '+12345', '1' * 16, '+' + '9' * 20])
def test_wa_me_link_is_none_for_unusable_numbers(bad):
    assert NS.generate_whatsapp_link(bad) is None            # never a broken https://wa.me/


def test_wa_me_message_is_url_encoded_and_cannot_inject_parameters():
    url = NS.generate_whatsapp_link('+50942882076', 'Salut & bienvenue #1 é 🙂 &text=evil')
    assert url.startswith('https://wa.me/50942882076?text=')
    query = url.split('?', 1)[1]
    assert query.count('=') == 1 and '&' not in query and '#' not in query and ' ' not in query


def test_ad_contact_link_names_the_ad_and_carries_its_url():
    ad = {'user_whatsapp': '+50942882076', 'title': 'iPhone 13', 'price_gkach': 250}
    url = NS.ad_contact_link(ad, viewer_whatsapp='+50937000000',
                             page_url='https://glory2yah.test/ad/abc-123')
    import urllib.parse as up
    text = up.unquote(url.split('text=', 1)[1])
    assert url.startswith('https://wa.me/50942882076?text=')
    assert 'iPhone 13' in text and '250 Gkach' in text and 'https://glory2yah.test/ad/abc-123' in text


def test_ad_contact_link_is_none_for_own_ad_and_missing_numbers():
    ad = {'user_whatsapp': '+50942882076', 'title': 'Mine'}
    assert NS.ad_contact_link(ad, viewer_whatsapp='50942882076') is None       # owner, other format
    assert NS.ad_contact_link({'user_whatsapp': '', 'title': 'x'}) is None
    assert NS.ad_contact_link({'user_whatsapp': None, 'title': 'x'}) is None
    assert NS.ad_contact_link({'title': 'x'}) is None


def test_ad_contact_link_sanitises_the_title():
    import urllib.parse as up
    ad = {'user_whatsapp': '+50942882076', 'title': 'Line1\nLine2\r\x00\x07 ' + 'x' * 200}
    text = up.unquote(NS.ad_contact_link(ad).split('text=', 1)[1])
    assert '\n' not in text and '\r' not in text and '\x00' not in text and '\x07' not in text
    assert len(text) < 140


def test_ad_contact_link_accepts_model_objects():
    ad = Ad(ad_id='a1', user_whatsapp='+50942882076', title='Chaise', description='d')
    assert NS.ad_contact_link(ad, viewer_whatsapp='+50911111111').startswith('https://wa.me/50942882076')


# -------------------------------- public ad page ------------------------------
@pytest.fixture()
def app():
    a = create_app('testing')
    a.config['WTF_CSRF_ENABLED'] = False
    yield a
    with a.app_context():
        db.session.remove()
        db.drop_all()


def _user(whatsapp):
    u = User(whatsapp=whatsapp, pseudo='p' + uuid.uuid4().hex[:10], name='T',
             auth_provider='whatsapp', is_active=True)
    u.set_password('Str0ng-Passw0rd!')
    db.session.add(u)
    db.session.commit()
    return u.id


def _ad(owner, title='Telephone Samsung'):
    ad = Ad(ad_id=str(uuid.uuid4()), user_whatsapp=owner, title=title,
            description='Bon etat', ad_type='sell', price_gkach=300, quantity=2,
            admin_status='approved', payment_status='approved')
    db.session.add(ad)
    db.session.commit()
    return ad.ad_id


def _client(app, uid=None):
    c = app.test_client()
    if uid:
        with c.session_transaction() as s:
            s['_user_id'] = str(uid)
            s['_fresh'] = True
    return c


def test_public_ad_page_has_a_working_contact_seller_link(app):
    with app.app_context():
        ad_id = _ad('+50942882076')
    page = _client(app).get(f'/ad/{ad_id}').data.decode()
    assert 'Telephone Samsung' in page, 'ad page did not render'
    assert 'https://wa.me/50942882076?text=' in page
    assert 'rel="noopener noreferrer"' in page
    assert f'/ad/{ad_id}' in page


def test_owner_does_not_get_a_contact_button_on_their_own_ad(app):
    with app.app_context():
        uid = _user('+50942882076')
        ad_id = _ad('+50942882076')
    page = _client(app, uid).get(f'/ad/{ad_id}').data.decode()
    assert 'Telephone Samsung' in page
    assert 'https://wa.me/50942882076' not in page


def test_other_logged_in_user_still_sees_the_contact_button(app):
    with app.app_context():
        uid = _user('+50937111222')
        ad_id = _ad('+50942882076')
    page = _client(app, uid).get(f'/ad/{ad_id}').data.decode()
    assert 'https://wa.me/50942882076?text=' in page


def test_ad_without_owner_number_shows_no_broken_link(app):
    with app.app_context():
        ad_id = _ad('')
    page = _client(app).get(f'/ad/{ad_id}').data.decode()
    assert 'Telephone Samsung' in page
    assert 'https://wa.me/?' not in page and 'wa.me/"' not in page


def test_requests_is_a_declared_dependency():
    """Regression: alerts import `requests` at runtime. It was missing from
    requirements.txt, so on a clean install (Render) every alert was silently
    skipped as 'requests unavailable' no matter how CALLMEBOT_APIKEY was set."""
    import re
    reqs = open(os.path.join(ROOT, 'requirements.txt')).read().lower().splitlines()
    assert any(re.match(r'^requests\s*(==|>=|~=|<|>|$)', l.strip()) for l in reqs)


def test_render_yaml_never_contains_the_callmebot_key_value():
    """The key is a secret: render.yaml must prompt for it (sync: false), not embed it."""
    import yaml
    doc = yaml.safe_load(open(os.path.join(ROOT, 'render.yaml')))
    env = {e['key']: e for e in doc['services'][0]['envVars']}
    assert env['CALLMEBOT_APIKEY'].get('sync') is False and 'value' not in env['CALLMEBOT_APIKEY']
    assert env['ADMIN_PASSWORD'].get('sync') is False and 'value' not in env['ADMIN_PASSWORD']
