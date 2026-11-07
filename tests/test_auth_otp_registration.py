import pytest

from app import create_app, db
from app.models.otp import OtpCode
from app.models.user import User
from app.services import otp_service


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
        assert OtpCode.query.filter_by(user_id=user.id).count() == 1
