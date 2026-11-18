"""Phase 3 tests: trial -> 1,000 GKach/month subscription on the EXISTING wallet."""
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

from app import create_app, db
from app.models.gkach_transaction import GkachTransaction
from app.models.user import User
from app.services.gkach_service import GkachService
from app.wifi import subscription_service as ss
from app.wifi import vendor_service as vs
from app.wifi.models import (WifiAuditLog, WifiSubscription,
                             WifiSubscriptionTransaction, WifiTrial, WifiVendor)
from app.wifi.policy import set_policy


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


def _vendor(balance=5000, admin=False):
    wa = '+5094' + str(uuid.uuid4().int)[:7]
    u = User(whatsapp=wa, pseudo='s' + uuid.uuid4().hex[:10], name='T',
             auth_provider='whatsapp', is_active=True, is_admin=admin)
    u.set_password('StrongPass123!')
    db.session.add(u)
    db.session.commit()
    if balance:
        GkachService.add_balance(wa, balance)
    return u, vs.register_vendor(u, 'Test Net') if not admin else None


def _bal(wa):
    return GkachService.get_balance(wa)


def _client(app, user_id):
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(user_id)
        s['_fresh'] = True
    return c


def _debits(wa):
    return GkachTransaction.query.filter_by(
        user_whatsapp=wa, transaction_type='wifi_subscription').count()


# ------------------------------- money rules --------------------------------
def test_renewal_debits_exactly_1000_and_records_ledger(ctx):
    u, v = _vendor(5000)
    r = ss.renew_subscription(v, 'key-aaaaaaaa')
    assert r['amount_gkach'] == 1000 and r['replayed'] is False
    assert _bal(u.whatsapp) == 4000
    led = GkachTransaction.query.filter_by(transaction_id=r['ledger_transaction_id']).one()
    assert led.amount == 1000 and led.transaction_type == 'wifi_subscription'
    assert led.old_balance == 5000 and led.new_balance == 4000 and led.status == 'completed'
    sub = WifiSubscription.query.filter_by(vendor_id=v.id).one()
    assert sub.period_end - sub.period_start == timedelta(days=30)


def test_first_period_starts_when_trial_ends(ctx):
    u, v = _vendor(5000)
    trial = WifiTrial.query.filter_by(vendor_id=v.id).one()
    ss.renew_subscription(v, 'key-aaaaaaaa')
    sub = WifiSubscription.query.filter_by(vendor_id=v.id).one()
    assert sub.period_start == trial.expires_at          # trial days are not wasted
    assert ss.access_state(v)['state'] == 'TRIAL'         # still in trial, already paid


def test_prepaid_period_becomes_subscribed_when_trial_ends(ctx):
    u, v = _vendor(5000)
    trial_end = WifiTrial.query.filter_by(vendor_id=v.id).one().expires_at
    ss.renew_subscription(v, 'key-aaaaaaaa')
    assert ss.access_state(v, trial_end - timedelta(minutes=1))['state'] == 'TRIAL'
    assert ss.access_state(v, trial_end + timedelta(minutes=1))['state'] == 'SUBSCRIBED'
    assert ss.access_state(v, trial_end + timedelta(days=30, minutes=1))['state'] == 'GRACE'


def test_insufficient_funds_never_debits_or_activates(ctx):
    u, v = _vendor(999)
    with pytest.raises(ss.InsufficientFunds):
        ss.renew_subscription(v, 'key-aaaaaaaa')
    assert _bal(u.whatsapp) == 999 and _debits(u.whatsapp) == 0
    assert WifiSubscription.query.filter_by(vendor_id=v.id).count() == 0
    failed = WifiSubscriptionTransaction.query.filter_by(vendor_id=v.id, status='FAILED').one()
    assert failed.failure_reason
    assert WifiAuditLog.query.filter_by(vendor_id=v.id, action='subscription.payment_failed').count() == 1
    # Same key can be retried after topping up; money moves once.
    GkachService.add_balance(u.whatsapp, 1)
    ss.renew_subscription(v, 'key-aaaaaaaa')
    assert _bal(u.whatsapp) == 0 and _debits(u.whatsapp) == 1


def test_no_wallet_account_is_a_clean_failure(ctx):
    u, v = _vendor(balance=0)
    with pytest.raises(ss.InsufficientFunds):
        ss.renew_subscription(v)
    assert WifiSubscription.query.filter_by(vendor_id=v.id).count() == 0


def test_same_idempotency_key_replays_without_second_debit(ctx):
    u, v = _vendor(5000)
    r1 = ss.renew_subscription(v, 'key-aaaaaaaa')
    r2 = ss.renew_subscription(v, 'key-aaaaaaaa')
    assert r2['replayed'] is True
    assert r2['ledger_transaction_id'] == r1['ledger_transaction_id']
    assert _bal(u.whatsapp) == 4000 and _debits(u.whatsapp) == 1
    assert WifiSubscription.query.filter_by(vendor_id=v.id).count() == 1


def test_double_click_with_new_key_is_refused_not_stacked(ctx):
    u, v = _vendor(5000)
    ss.renew_subscription(v, 'key-aaaaaaaa')
    with pytest.raises(ss.RenewalNotDue):
        ss.renew_subscription(v, 'key-bbbbbbbb')
    assert _bal(u.whatsapp) == 4000 and _debits(u.whatsapp) == 1


def test_concurrent_duplicate_period_rolls_back_the_debit(ctx, monkeypatch):
    """Simulates a race: both requests read the same stale state."""
    u, v = _vendor(5000)
    stale = ss.effective_until(v)
    ss.renew_subscription(v, 'key-aaaaaaaa')
    assert _bal(u.whatsapp) == 4000
    monkeypatch.setattr(ss, 'effective_until', lambda vendor: stale)
    with pytest.raises(ss.RenewalConflict):
        ss.renew_subscription(v, 'key-bbbbbbbb')
    assert _bal(u.whatsapp) == 4000 and _debits(u.whatsapp) == 1   # debit rolled back
    assert WifiSubscription.query.filter_by(vendor_id=v.id).count() == 1


def test_crash_after_debit_before_commit_loses_no_money(ctx, monkeypatch):
    u, v = _vendor(5000)
    monkeypatch.setattr(ss, 'audit', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('boom')))
    with pytest.raises(RuntimeError):
        ss.renew_subscription(v, 'key-aaaaaaaa')
    db.session.rollback()   # what Flask teardown does for an unhandled error
    assert _bal(u.whatsapp) == 5000 and _debits(u.whatsapp) == 0
    assert WifiSubscription.query.filter_by(vendor_id=v.id).count() == 0


def test_suspended_vendor_is_not_charged(ctx):
    u, v = _vendor(5000)
    vs.suspend_vendor(v, 'abuse')
    db.session.commit()
    with pytest.raises(ss.VendorNotActive):
        ss.renew_subscription(v)
    assert _bal(u.whatsapp) == 5000


def test_price_comes_from_super_admin_policy(ctx):
    set_policy('subscription_price_gkach', 1500)
    db.session.commit()
    try:
        u, v = _vendor(5000)
        r = ss.renew_subscription(v)
        assert r['amount_gkach'] == 1500 and _bal(u.whatsapp) == 3500
    finally:
        set_policy('subscription_price_gkach', 1000)
        db.session.commit()


def test_invalid_idempotency_key_rejected(ctx):
    u, v = _vendor(5000)
    with pytest.raises(ss.SubscriptionError):
        ss.renew_subscription(v, 'short')
    assert _bal(u.whatsapp) == 5000


# ----------------------------- access / grace rules -------------------------
def test_state_machine_trial_grace_expired_and_entitlements_protected(ctx):
    u, v = _vendor(0)
    trial_end = WifiTrial.query.filter_by(vendor_id=v.id).one().expires_at
    s = ss.access_state(v, trial_end - timedelta(hours=1))
    assert s['state'] == 'TRIAL' and s['can_sell']
    s = ss.access_state(v, trial_end + timedelta(hours=1))
    assert s['state'] == 'GRACE' and s['can_sell'] and s['existing_entitlements_protected']
    s = ss.access_state(v, trial_end + timedelta(days=3, minutes=1))
    assert s['state'] == 'EXPIRED'
    assert not s['can_sell'] and not s['can_activate_customers']
    assert s['existing_entitlements_protected'] is True


def test_grace_zero_means_immediate_block(ctx):
    set_policy('offline_grace_days', 0)
    db.session.commit()
    try:
        u, v = _vendor(0)
        end = WifiTrial.query.filter_by(vendor_id=v.id).one().expires_at
        assert ss.access_state(v, end + timedelta(seconds=1))['state'] == 'EXPIRED'
    finally:
        set_policy('offline_grace_days', 3)
        db.session.commit()


def test_renewal_after_expiry_starts_now_and_restores_access(ctx, monkeypatch):
    u, v = _vendor(5000)
    end = WifiTrial.query.filter_by(vendor_id=v.id).one().expires_at
    later = end + timedelta(days=10)
    monkeypatch.setattr(ss, 'utcnow', lambda: later)
    assert ss.access_state(v, later)['state'] == 'EXPIRED'
    ss.renew_subscription(v, 'key-aaaaaaaa')
    sub = WifiSubscription.query.filter_by(vendor_id=v.id).one()
    assert sub.period_start == later and sub.period_end == later + timedelta(days=30)
    st = ss.access_state(v, later + timedelta(days=1))
    assert st['state'] == 'SUBSCRIBED' and st['can_sell']


def test_no_plan_state_when_trial_was_consumed_before(ctx):
    wa = '+5094' + str(uuid.uuid4().int)[:7]
    u = User(whatsapp=wa, pseudo='n' + uuid.uuid4().hex[:10], name='T',
             auth_provider='whatsapp', is_active=True)
    u.set_password('StrongPass123!')
    db.session.add(u)
    db.session.commit()
    from app.wifi.models import WifiTrialLedger
    db.session.add(WifiTrialLedger(identity_hash=vs.identity_hash(wa)))
    db.session.commit()
    v = vs.register_vendor(u, 'Returning Vendor')
    st = ss.access_state(v)
    assert st['state'] == 'NO_PLAN' and not st['can_sell']


def test_trial_warning_sent_once(ctx):
    u, v = _vendor(0)
    t = WifiTrial.query.filter_by(vendor_id=v.id).one()
    now = t.expires_at - timedelta(hours=2)
    assert ss.send_trial_warnings(now) == 1
    assert ss.send_trial_warnings(now) == 0
    db.session.refresh(t)
    assert t.warned_at == now


# ----------------------------------- HTTP -----------------------------------
def test_http_renew_replay_insufficient_and_isolation(app):
    with app.app_context():
        u1, v1 = _vendor(5000)
        u2, v2 = _vendor(0)
        admin, _ = _vendor(0, admin=True)
        ids = (u1.id, u2.id, admin.id, v1.id, v2.id)
        wa1 = u1.whatsapp
    uid1, uid2, aid, vid1, vid2 = ids

    h = {'Idempotency-Key': 'http-key-0001'}
    r1 = _client(app, uid1).post('/wifi/vendor/subscription/renew', headers=h)
    r2 = _client(app, uid1).post('/wifi/vendor/subscription/renew', headers=h)
    assert r1.status_code == 201 and r2.status_code == 200 and r2.json['replayed']
    with app.app_context():
        assert _bal(wa1) == 4000 and _debits(wa1) == 1

    assert _client(app, uid2).post('/wifi/vendor/subscription/renew',
                                   headers={'Idempotency-Key': 'http-key-0002'}).status_code == 402
    assert _client(app, uid1).post('/wifi/vendor/subscription/renew',
                                   headers={'Idempotency-Key': 'http-key-0003'}).status_code == 409

    sub = _client(app, uid1).get('/wifi/vendor/subscription').json
    assert sub['balance_gkach'] == 4000 and sub['price_gkach'] == 1000
    assert [x['status'] for x in sub['history']] == ['COMPLETED']      # only OWN history
    other = _client(app, uid2).get('/wifi/vendor/subscription').json
    assert [x['status'] for x in other['history']] == ['FAILED']

    assert _client(app, uid1).get(
        f'/wifi/admin/vendors/{vid2}/subscription-history').status_code in (302, 401, 403)
    adm = _client(app, aid).get(f'/wifi/admin/vendors/{vid1}/subscription-history')
    assert adm.status_code == 200 and adm.json['history'][0]['amount_gkach'] == 1000
    lst = _client(app, aid).get('/wifi/admin/subscriptions?state=TRIAL')
    assert lst.status_code == 200 and len(lst.json['subscriptions']) == 2
