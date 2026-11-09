import pytest

from app import create_app, db
from app.models.otp import OtpCode
from app.models.user import User
from app.services import notification_service, otp_service


@pytest.fixture
def app():
    test_app = create_app('testing')
    yield test_app
    with test_app.app_context():
        db.session.remove()
        db.drop_all()


def test_registration_creates_pending_account_and_otp(app, monkeypatch):
    monkeypatch.setattr(otp_service, 'send_code', lambda otp, code: 'test')
    client = app.test_client()

    response = client.post('/auth/register', data={
        'name': 'Test User',
        'pseudo': 'otp_test_user',
        'whatsapp': '+50942882076',
        'password': 'pass123',
    })

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/auth/verify')
    with app.app_context():
        user = User.query.filter_by(pseudo='otp_test_user').one()
        assert user.is_active is False
        assert user.phone_verified is False
        otp = OtpCode.query.filter_by(user_id=user.id).one()
        assert otp.phone == user.whatsapp == '+50942882076'


def test_phone_normalization_matches_user_format_and_keeps_legacy_lookup(app):
    assert otp_service.normalize_phone('+509 4288-2076') == '+50942882076'
    assert otp_service.phone_variants('+50942882076') == (
        '+50942882076', '50942882076'
    )
    with app.app_context():
        otp, code = otp_service.issue('+50942882076')
        otp.phone = '50942882076'
        db.session.commit()
        assert OtpCode.pending_for('+50942882076') is otp
        assert otp_service.verify('+50942882076', code)[0] == otp_service.OK


def test_send_code_uses_digits_for_whatsapp_provider(app, monkeypatch):
    provider_args = {}

    def fake_send(message, phone, allow_callmebot=False):
        provider_args['phone'] = phone
        provider_args['allow_callmebot'] = allow_callmebot
        return 'test'

    monkeypatch.setattr('app.services.notification_service._send_whatsapp_alert', fake_send)
    with app.app_context():
        otp, delivered_via = otp_service.issue_and_send('+50940000001')
        assert delivered_via == 'test'
        assert otp.phone == '+50940000001'
        assert provider_args['phone'] == '50940000001'
        assert provider_args['allow_callmebot'] is False


def test_send_code_skips_callmebot_for_admin_number_too(app, monkeypatch):
    provider_args = {}

    def fake_send(message, phone, allow_callmebot=False):
        provider_args['phone'] = phone
        provider_args['allow_callmebot'] = allow_callmebot
        return 'ultramsg'

    monkeypatch.setattr('app.services.notification_service._send_whatsapp_alert', fake_send)
    with app.app_context():
        otp, delivered_via = otp_service.issue_and_send('+50942882076')
        assert delivered_via == 'ultramsg'
        assert provider_args == {
            'phone': '50942882076',
            'allow_callmebot': False,
        }


def test_admin_alerts_explicitly_allow_callmebot(monkeypatch):
    sent = {}

    def fake_send(message, phone=None, allow_callmebot=False):
        sent['allow_callmebot'] = allow_callmebot

    class ImmediateThread:
        def __init__(self, target, args=(), kwargs=None, daemon=None):
            self.target = target
            self.args = args
            self.kwargs = kwargs or {}

        def start(self):
            self.target(*self.args, **self.kwargs)

    monkeypatch.setattr(notification_service, '_alerts_enabled', lambda: True)
    monkeypatch.setattr(notification_service, '_send_whatsapp_alert', fake_send)
    monkeypatch.setattr(notification_service.threading, 'Thread', ImmediateThread)

    notification_service.alert_admin('Admin panel notification')

    assert sent['allow_callmebot'] is True


def test_dev_fallback_requires_debug_and_nonproduction_environment(app, monkeypatch):
    monkeypatch.delenv('RENDER', raising=False)
    monkeypatch.delenv('RENDER_SERVICE_ID', raising=False)
    monkeypatch.delenv('RENDER_EXTERNAL_URL', raising=False)
    monkeypatch.delenv('FLASK_ENV', raising=False)
    monkeypatch.delenv('PORT', raising=False)
    monkeypatch.setattr('app.services.notification_service._send_whatsapp_alert',
                        lambda message, phone, allow_callmebot=False: None)

    with app.app_context():
        app.config['DEBUG'] = True
        monkeypatch.setenv('FLASK_ENV', 'production')
        otp, delivered_via = otp_service.issue_and_send('+50942882076')
        assert delivered_via is None
        assert not hasattr(otp, 'dev_code')

        monkeypatch.delenv('FLASK_ENV')
        otp, delivered_via = otp_service.issue_and_send('+50942882076')
        assert delivered_via == 'dev_fallback'
        assert len(otp.dev_code) == 6

        app.config['DEBUG'] = False
        otp, delivered_via = otp_service.issue_and_send('+50942882077')
        assert delivered_via is None
        assert not hasattr(otp, 'dev_code')
