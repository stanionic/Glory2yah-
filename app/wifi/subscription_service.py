"""Trial + 1,000 GKach/month subscription, built on the EXISTING wallet.

Money safety (never charge twice for one renewal):
  1. debit, ledger row, transaction row and subscription row share ONE DB
     transaction: any failure rolls the debit back too;
  2. idempotency key per vendor  -> a retried request replays the stored result;
  3. UNIQUE(vendor_id, period_start) -> concurrent requests for the same period
     cannot both commit;
  4. renewal is only allowed inside the renewal window, so a double click after
     success is refused instead of stacking a second period.
"""
import re
import uuid
from datetime import timedelta

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app import db
from app.services.gkach_service import GkachService
from app.models.gkach_transaction import GkachTransaction
from app.utils.validators import ValidationError
from app.wifi.models import (
    WifiSubscription, WifiSubscriptionTransaction, WifiTrial, WifiVendor,
    VENDOR_ACTIVE,
)
from app.wifi.policy import get_policy
from app.wifi.vendor_service import audit, utcnow

LEDGER_TYPE = 'wifi_subscription'
_KEY_RE = re.compile(r'^[A-Za-z0-9_\-]{8,64}$')


class SubscriptionError(Exception):
    status_code = 400


class VendorNotActive(SubscriptionError):
    status_code = 403


class RenewalNotDue(SubscriptionError):
    status_code = 409


class InsufficientFunds(SubscriptionError):
    status_code = 402


class RenewalConflict(SubscriptionError):
    status_code = 409


def effective_until(vendor):
    """Latest end among the trial and all paid periods (None = never had a plan)."""
    ends = []
    trial = WifiTrial.query.filter_by(vendor_id=vendor.id).first()
    if trial:
        ends.append(trial.expires_at)
    sub_end = db.session.query(func.max(WifiSubscription.period_end)).filter_by(
        vendor_id=vendor.id).scalar()
    if sub_end:
        ends.append(sub_end)
    return max(ends) if ends else None


def access_state(vendor, now=None):
    """Single source of truth for what a vendor may do.

    GRACE = within ``offline_grace_days`` after expiry: still operating, clearly
    flagged. EXPIRED = no NEW sales/activations. Existing prepaid customer
    entitlements are protected in EVERY state.
    """
    now = now or utcnow()
    until = effective_until(vendor)
    grace = timedelta(days=get_policy('offline_grace_days'))
    base = {'existing_entitlements_protected': True,
            'effective_until': until.isoformat() if until else None,
            'grace_ends_at': (until + grace).isoformat() if until else None}
    if vendor.status != VENDOR_ACTIVE:
        state = 'SUSPENDED'
    elif until is None:
        state = 'NO_PLAN'
    elif now < until:
        # SUBSCRIBED only when a PAID period is running right now; a period
        # bought in advance (during the trial) does not start before the trial ends.
        paid_now = WifiSubscription.query.filter(
            WifiSubscription.vendor_id == vendor.id,
            WifiSubscription.period_start <= now,
            WifiSubscription.period_end > now).first()
        state = 'SUBSCRIBED' if paid_now else 'TRIAL'
    elif now < until + grace:
        state = 'GRACE'
    else:
        state = 'EXPIRED'
    can_sell = state in ('SUBSCRIBED', 'TRIAL', 'GRACE')
    base.update(state=state, can_sell=can_sell, can_activate_customers=can_sell,
                next_billing_date=base['effective_until'])
    return base


def _validate_key(key):
    if key is None:
        return None
    if not _KEY_RE.match(key):
        raise SubscriptionError('Idempotency key must be 8-64 chars [A-Za-z0-9_-]')
    return key


def _result(sub, txn, replayed):
    return {'replayed': replayed, 'period_start': sub.period_start.isoformat(),
            'period_end': sub.period_end.isoformat(), 'amount_gkach': sub.amount_gkach,
            'ledger_transaction_id': txn.ledger_transaction_id, 'status': txn.status}


def _replay(vendor_id, key):
    txn = WifiSubscriptionTransaction.query.filter_by(
        vendor_id=vendor_id, idempotency_key=key, status='COMPLETED').first()
    if txn is None:
        return None
    sub = WifiSubscription.query.filter_by(transaction_id=txn.id).first()
    return _result(sub, txn, True)


def renew_subscription(vendor, idempotency_key=None, ip=None, actor_user_id=None):
    key = _validate_key(idempotency_key)
    if key:
        done = _replay(vendor.id, key)
        if done:
            return done

    # Serialise renewals of one vendor where the DB supports row locks.
    vendor = db.session.query(WifiVendor).filter_by(id=vendor.id).with_for_update().one()
    if vendor.status != VENDOR_ACTIVE:
        raise VendorNotActive('Vendor account is not active')

    now = utcnow()
    until = effective_until(vendor)
    window = timedelta(days=get_policy('renewal_window_days'))
    if until and until - now > window:
        raise RenewalNotDue(f'Subscription is paid until {until.isoformat()}; '
                            f'renewal opens {get_policy("renewal_window_days")} days before')

    start = max(now, until) if until else now
    end = start + timedelta(days=get_policy('subscription_period_days'))
    price = get_policy('subscription_price_gkach')
    ref = str(uuid.uuid4())
    whatsapp = vendor.user.whatsapp

    try:
        GkachService.deduct_balance(
            whatsapp, price, transaction_type=LEDGER_TYPE, _commit=False,
            description=f'UWZ subscription {vendor.vendor_uid} ref={ref}')
    except ValidationError as e:
        db.session.rollback()
        _record_failure(vendor.id, price, str(e), ip, actor_user_id)
        raise InsufficientFunds(str(e))

    ledger = GkachTransaction.query.filter(
        GkachTransaction.user_whatsapp == whatsapp,
        GkachTransaction.transaction_type == LEDGER_TYPE,
        GkachTransaction.description.like(f'%ref={ref}')).one()

    txn = WifiSubscriptionTransaction(
        vendor_id=vendor.id, idempotency_key=key, amount_gkach=price,
        status='COMPLETED', ledger_transaction_id=ledger.transaction_id)
    db.session.add(txn)
    db.session.flush()
    sub = WifiSubscription(vendor_id=vendor.id, period_start=start, period_end=end,
                           amount_gkach=price, transaction_id=txn.id)
    db.session.add(sub)
    audit('subscription.renewed', vendor.id, actor_user_id,
          f'{price} GKach until {end.isoformat()} ledger={ledger.transaction_id}', ip)
    try:
        db.session.commit()          # debit + ledger + txn + subscription, atomically
    except IntegrityError:
        db.session.rollback()        # the debit is rolled back with it
        if key:
            done = _replay(vendor.id, key)
            if done:
                return done
        raise RenewalConflict('A renewal for this period is already being processed')
    GkachService._invalidate_balance_cache(whatsapp)
    _notify(vendor, 'Abonnement UWZ renouvelé',
            f'{price} GKach débités. Actif jusqu’au {end:%d/%m/%Y}.')
    return _result(sub, txn, False)


def _record_failure(vendor_id, price, reason, ip, actor_user_id):
    db.session.add(WifiSubscriptionTransaction(
        vendor_id=vendor_id, idempotency_key=None, amount_gkach=price,
        status='FAILED', failure_reason=reason[:255]))
    audit('subscription.payment_failed', vendor_id, actor_user_id, reason[:255], ip)
    db.session.commit()
    vendor = db.session.get(WifiVendor, vendor_id)
    _notify(vendor, 'Paiement UWZ refusé',
            'Solde GKach insuffisant : rechargez votre portefeuille puis réessayez.')


def _notify(vendor, title, message):
    """Best-effort: a notification failure must never affect a payment."""
    try:
        from app.services.notification_hub import NotificationHub
        NotificationHub.create(recipient_id=vendor.user_id, title=title, message=message,
                               category='system', entity_type='wifi_vendor',
                               entity_id=vendor.id, aggregate=False, force=True)
    except Exception:
        pass


def send_trial_warnings(now=None):
    """Warn vendors whose trial ends within ``trial_warning_hours``. Run from cron."""
    now = now or utcnow()
    horizon = now + timedelta(hours=get_policy('trial_warning_hours'))
    due = WifiTrial.query.filter(WifiTrial.warned_at.is_(None),
                                 WifiTrial.expires_at > now,
                                 WifiTrial.expires_at <= horizon).all()
    for trial in due:
        vendor = db.session.get(WifiVendor, trial.vendor_id)
        trial.warned_at = now
        _notify(vendor, 'Votre essai UWZ se termine bientôt',
                f'Fin de l’essai le {trial.expires_at:%d/%m/%Y %H:%M}. '
                'Abonnez-vous (1000 GKach/mois) pour continuer à vendre.')
    db.session.commit()
    return len(due)


def history(vendor_id, limit=50):
    rows = WifiSubscriptionTransaction.query.filter_by(vendor_id=vendor_id).order_by(
        WifiSubscriptionTransaction.id.desc()).limit(limit).all()
    return [{'at': r.created_at.isoformat(), 'amount_gkach': r.amount_gkach,
             'status': r.status, 'ledger_transaction_id': r.ledger_transaction_id,
             'failure_reason': r.failure_reason} for r in rows]
