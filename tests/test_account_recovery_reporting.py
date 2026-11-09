import pytest

from app import create_app, db
from app.models.account_report import AccountReport
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


def _create_user(pseudo, whatsapp, *, is_admin=False):
    user = User(
        pseudo=pseudo,
        name=pseudo,
        whatsapp=whatsapp,
        is_active=True,
        phone_verified=True,
        is_admin=is_admin,
    )
    user.set_password('old-password')
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, user_id):
    with client.session_transaction() as session:
        session['_user_id'] = str(user_id)
        session['_fresh'] = True


def test_password_recovery_requires_otp_and_changes_password(app, monkeypatch):
    monkeypatch.setattr(otp_service, 'generate_code', lambda: '123456')
    monkeypatch.setattr(otp_service, 'send_code', lambda otp, code: 'test')
    client = app.test_client()

    with app.app_context():
        user = _create_user('recover_me', '+50940000001')
        user_id = user.id

    response = client.post('/auth/forgot-password', data={
        'action': 'send_code',
        'identifier': 'recover_me',
    })
    assert response.status_code == 200
    assert b'temp-password' not in response.data

    with app.app_context():
        otp = OtpCode.query.filter_by(
            user_id=user_id, purpose=OtpCode.PURPOSE_PASSWORD_RESET
        ).one()
        assert otp.code_hash != '123456'

    response = client.post('/auth/forgot-password', data={
        'action': 'reset_password',
        'code': '123456',
        'new_password': 'new-password',
        'confirm_password': 'new-password',
    })
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/auth/login')

    with app.app_context():
        user = db.session.get(User, user_id)
        assert user.check_password('new-password')
        assert not user.check_password('old-password')


def test_reported_account_is_searchable_and_admin_can_delete_it(app):
    reporter_client = app.test_client()
    admin_client = app.test_client()
    with app.app_context():
        reporter = _create_user('reporter', '+50940000002')
        target = _create_user('suspicious', '+50940000003')
        admin = _create_user('moderator', '+50940000004', is_admin=True)
        reporter_id, target_id, admin_id = reporter.id, target.id, admin.id

    _login(reporter_client, reporter_id)
    response = reporter_client.get('/auth/report-account?q=suspicious')
    assert response.status_code == 200
    assert b'@suspicious' in response.data

    response = reporter_client.post(
        f'/auth/report-account/{target_id}',
        data={'reason': 'Kont sa a ap pibliye fo piblisite.'},
    )
    assert response.status_code == 302
    with app.app_context():
        assert AccountReport.query.filter_by(
            reporter_id=reporter_id, reported_user_id=target_id, status='open'
        ).count() == 1

    _login(admin_client, admin_id)
    response = admin_client.get('/admin/users/reported?q=suspicious')
    assert response.status_code == 200
    assert b'Kont sa a ap pibliye fo piblisite.' in response.data

    response = admin_client.post(f'/admin/users/{target_id}/delete')
    assert response.status_code == 302
    with app.app_context():
        assert db.session.get(User, target_id) is None
        assert AccountReport.query.filter_by(reported_user_id=target_id).count() == 0


def test_users_cannot_report_themselves(app):
    client = app.test_client()
    with app.app_context():
        user = _create_user('self_reporter', '+50940000005')
        user_id = user.id

    _login(client, user_id)
    response = client.post(
        f'/auth/report-account/{user_id}',
        data={'reason': 'I am reporting myself.'},
    )
    assert response.status_code == 302
    with app.app_context():
        assert AccountReport.query.count() == 0


def test_only_admin_can_dismiss_user_reports(app):
    user_client = app.test_client()
    admin_client = app.test_client()
    with app.app_context():
        reporter = _create_user('flag_reporter', '+50940000008')
        target = _create_user('flag_target', '+50940000009')
        admin = _create_user('flag_admin', '+50940000010', is_admin=True)
        db.session.add(AccountReport(
            reporter_id=reporter.id,
            reported_user_id=target.id,
            reason='This account is posting suspicious content.',
        ))
        db.session.commit()
        target_id = target.id
        admin_id = admin.id

    _login(user_client, target_id)
    response = user_client.post(f'/admin/users/reports/{target_id}/dismiss')
    assert response.status_code == 302
    with app.app_context():
        report = AccountReport.query.filter_by(reported_user_id=target_id).one()
        assert report.status == 'open'

    _login(admin_client, admin_id)
    response = admin_client.post(f'/admin/users/reports/{target_id}/dismiss')
    assert response.status_code == 302
    with app.app_context():
        report = AccountReport.query.filter_by(reported_user_id=target_id).one()
        assert report.status == 'dismissed'
