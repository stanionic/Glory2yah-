"""Phase 2 tests: vendor registration, single free trial, tenant isolation, authz.

Service-level tests use the ``ctx`` fixture (one app context). HTTP tests do NOT
hold an app context while calling the client: Flask-Login caches the user in
``g``, which would leak between requests.
"""
import os
import sys
import uuid
from datetime import timedelta

import pytest

os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('SECRET_KEY', 'uwz-tests-secret')
os.environ.setdefault('WTF_CSRF_ENABLED', 'False')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from werkzeug.exceptions import NotFound

from app import create_app, db
from app.models.user import User
from app.wifi import vendor_service as vs
from app.wifi.models import WifiAuditLog, WifiTrial, WifiTrialLedger, WifiVendor
from app.wifi.policy import set_policy
from app.wifi.tenancy import TenantViolation, get_owned, tenant_query


@pytest.fixture()
def app():
    test_app = create_app('testing')
    test_app.config['WTF_CSRF_ENABLED'] = False
    yield test_app
    with test_app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def ctx(app):
    with app.app_context():
        yield app
        db.session.rollback()


def _user(admin=False, whatsapp=None):
    n = whatsapp or '+509' + str(uuid.uuid4().int)[:8]
    u = User(whatsapp=n, pseudo='w' + uuid.uuid4().hex[:10], name='T',
             auth_provider='whatsapp', is_active=True, is_admin=admin)
    u.set_password('StrongPass123!')
    db.session.add(u)
    db.session.commit()
    return u


def _client(app, user_id):
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(user_id)
        s['_fresh'] = True
    return c


# ------------------------------ service level ------------------------------
def test_register_starts_single_trial_of_policy_length(ctx):
    v = vs.register_vendor(_user(), 'Cyber Haiti')
    assert v.status == 'ACTIVE' and v.vendor_uid.startswith('UWZ-')
    t = WifiTrial.query.filter_by(vendor_id=v.id).one()
    assert t.expires_at - t.started_at == timedelta(days=3)


def test_duplicate_registration_rejected(ctx):
    u = _user()
    vs.register_vendor(u, 'Shop A')
    with pytest.raises(vs.VendorError):
        vs.register_vendor(u, 'Shop B')


def test_invalid_business_name_rejected(ctx):
    with pytest.raises(vs.VendorError):
        vs.register_vendor(_user(), 'x')


def test_trial_not_regranted_after_hard_deleted_account_reregisters(ctx):
    wa = '+509' + str(uuid.uuid4().int)[:8]
    u1 = _user(whatsapp=wa)
    v1 = vs.register_vendor(u1, 'First')
    assert WifiTrial.query.filter_by(vendor_id=v1.id).count() == 1
    # Hard-delete everything tied to the account (worst case for abuse).
    WifiTrial.query.filter_by(vendor_id=v1.id).delete()
    WifiAuditLog.query.filter_by(vendor_id=v1.id).delete()
    db.session.delete(v1)
    db.session.delete(u1)
    db.session.commit()
    assert WifiTrialLedger.query.filter_by(identity_hash=vs.identity_hash(wa)).count() == 1

    v2 = vs.register_vendor(_user(whatsapp=wa), 'Second')
    assert v2.status == 'ACTIVE'                       # account works...
    assert WifiTrial.query.filter_by(vendor_id=v2.id).count() == 0   # ...no new trial
    assert vs.trial_status(v2)['state'] == 'NONE'


def test_trial_identity_is_hashed_not_plaintext(ctx):
    wa = '+509' + str(uuid.uuid4().int)[:8]
    vs.register_vendor(_user(whatsapp=wa), 'Hash Shop')
    row = WifiTrialLedger.query.filter_by(identity_hash=vs.identity_hash(wa)).one()
    assert wa.lstrip('+') not in row.identity_hash and len(row.identity_hash) == 64


def test_approval_mode_defers_trial_until_admin_activates(ctx):
    set_policy('vendor_approval_required', 1)
    db.session.commit()
    try:
        v = vs.register_vendor(_user(), 'Needs Approval')
        assert v.status == 'PENDING'
        assert WifiTrial.query.filter_by(vendor_id=v.id).count() == 0
        vs.activate_vendor(v)
        db.session.commit()
        assert WifiTrial.query.filter_by(vendor_id=v.id).count() == 1
        vs.suspend_vendor(v, 'abuse')
        vs.activate_vendor(v)  # reactivation must NOT restart the trial
        db.session.commit()
        assert WifiTrial.query.filter_by(vendor_id=v.id).count() == 1
    finally:
        set_policy('vendor_approval_required', 0)
        db.session.commit()


def test_default_policy_needs_no_admin_approval(ctx):
    """Product decision: the free trial never requires Super Admin approval."""
    v = vs.register_vendor(_user(), 'No Approval Needed')
    assert v.status == 'ACTIVE'
    assert vs.trial_status(v)['state'] == 'ACTIVE'


def test_trial_needs_no_deposit_no_phone_verification_no_admin(ctx):
    """Product decision: the trial is completely free; only a normal account is needed."""
    from app.models.user_gkach import UserGkach
    u = _user()
    assert u.phone_verified in (False, None) and u.is_admin is False
    assert UserGkach.query.filter_by(user_id=u.id).count() == 0     # no wallet, no deposit
    v = vs.register_vendor(u, 'Free Trial Shop')
    assert v.status == 'ACTIVE' and vs.trial_status(v)['state'] == 'ACTIVE'


def test_tenant_query_isolates_and_foreign_id_is_404(ctx):
    v1 = vs.register_vendor(_user(), 'Vendor One')
    v2 = vs.register_vendor(_user(), 'Vendor Two')
    t2 = WifiTrial.query.filter_by(vendor_id=v2.id).one()
    assert [t.vendor_id for t in tenant_query(WifiTrial, v1.id)] == [v1.id]
    with pytest.raises(NotFound):
        get_owned(WifiTrial, t2.id, v1.id)
    assert get_owned(WifiTrial, t2.id, v2.id).id == t2.id


def test_tenant_query_refuses_non_tenant_models(ctx):
    with pytest.raises(TypeError):
        tenant_query(WifiVendor, 1)


def test_flush_guard_blocks_cross_tenant_write(ctx):
    v1 = vs.register_vendor(_user(), 'Vendor One')
    v2 = vs.register_vendor(_user(), 'Vendor Two')
    t2 = WifiTrial.query.filter_by(vendor_id=v2.id).one()
    with ctx.test_request_context('/'):
        from flask import g
        g.wifi_vendor_id = v1.id
        t2.warned_at = vs.utcnow()
        with pytest.raises(TenantViolation):
            db.session.flush()
    db.session.rollback()


# -------------------------------- HTTP level --------------------------------
def test_vendor_endpoints_authz_and_registration(app):
    assert app.test_client().get('/wifi/vendor/dashboard').status_code == 401
    with app.app_context():
        uid = _user().id
    c = _client(app, uid)
    assert c.get('/wifi/vendor/dashboard').status_code == 403          # not a vendor yet
    r = c.post('/wifi/vendor/register', json={'business_name': 'Via API'})
    assert r.status_code == 201 and r.json['trial']['state'] == 'ACTIVE'
    d = _client(app, uid).get('/wifi/vendor/dashboard')
    assert d.status_code == 200 and d.json['vendor']['business_name'] == 'Via API'
    assert _client(app, uid).post('/wifi/vendor/register',
                                  json={'business_name': 'Again'}).status_code == 400


def test_vendor_cannot_use_admin_endpoints_and_admin_can(app):
    with app.app_context():
        vendor_uid, admin_uid = _user().id, _user(admin=True).id
    assert _client(app, vendor_uid).post(
        '/wifi/vendor/register', json={'business_name': 'Shop Z'}).status_code == 201
    with app.app_context():
        vid = WifiVendor.query.filter_by(user_id=vendor_uid).one().id

    vc = _client(app, vendor_uid)
    assert vc.get('/wifi/admin/vendors').status_code in (302, 401, 403)
    assert vc.post(f'/wifi/admin/vendors/{vid}/suspend').status_code in (302, 401, 403)
    assert vc.post('/wifi/admin/policy', json={'trial_days': 365}).status_code in (302, 401, 403)
    with app.app_context():
        assert db.session.get(WifiVendor, vid).status == 'ACTIVE'

    ac = _client(app, admin_uid)
    assert ac.get('/wifi/admin/vendors').status_code == 200
    r = ac.post(f'/wifi/admin/vendors/{vid}/suspend', json={'reason': 'test'})
    assert r.status_code == 200 and r.json['vendor']['status'] == 'SUSPENDED'
    assert _client(app, vendor_uid).get('/wifi/vendor/dashboard').status_code == 200
    with app.app_context():
        assert WifiAuditLog.query.filter_by(vendor_id=vid, action='vendor.suspended').count() == 1
    assert ac.post('/wifi/admin/policy', json={'trial_days': -1}).status_code == 400
    assert ac.post('/wifi/admin/policy', json={'bogus': 1}).status_code == 400


def test_suspended_vendor_blocked_from_active_only_endpoints(app):
    from flask import jsonify
    from app.wifi.tenancy import wifi_vendor_required

    @app.get('/_t/active_only')
    @wifi_vendor_required()
    def _active_only():
        return jsonify(ok=True)

    with app.app_context():
        u = _user()
        v = vs.register_vendor(u, 'Soon Suspended')
        uid, vid = u.id, v.id
    assert _client(app, uid).get('/_t/active_only').status_code == 200
    with app.app_context():
        vs.suspend_vendor(db.session.get(WifiVendor, vid), 'x')
        db.session.commit()
    r = _client(app, uid).get('/_t/active_only')
    assert r.status_code == 403 and r.json['status'] == 'SUSPENDED'
