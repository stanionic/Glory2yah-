"""KONFERANS monthly subscription (500 Gkach / mwa).

Replaces the old pay-as-you-go billing (250 Gkach pa lè). A room runs free for
FREE_MINUTES_DEFAULT (45) minutes; past that window the owner needs an
entitled subscription, which buys UNLIMITED conference time for the whole
month across every room they own.

Rules mirror the Jere Biznis subscription (app/models/jere_biznis.py) so the
two modules behave identically for the user:
  - price is 500 Gkach/month;
  - multi-month prepayment (1/3/6/12/custom) is supported;
  - an extension STACKS on the current expiration instead of resetting it;
  - a payment is idempotent: the same idempotency_key can never charge twice;
  - a lapsed subscription never deletes rooms or recordings.
"""
from datetime import datetime, timedelta
import uuid

from app import db
from app.models.konferans import KonferansSubscription, KonferansPayment
from app.services.gkach_service import GkachService
from app.utils.validators import ValidationError

MONTHLY_PRICE_GKACH = 500
# A "month" is credited as 30 days so the period is deterministic and matches
# the Jere Biznis prepayment behaviour.
MONTH_DAYS = 30
MIN_MONTHS = 1
MAX_MONTHS = 120


def _add_months(base, months):
    """Credit `months` by adding MONTH_DAYS per month (no calendar drift)."""
    return base + timedelta(days=MONTH_DAYS * max(1, int(months)))


def get_subscription(user_id):
    """The user's subscription row, or None when they never paid."""
    if user_id is None:
        return None
    try:
        return KonferansSubscription.query.filter_by(user_id=int(user_id)).first()
    except Exception:
        # Missing table on an unmigrated DB must not break room loading.
        db.session.rollback()
        return None


def state_for_user(user):
    """Serialised subscription state, safe to fold into a JSON response."""
    sub = get_subscription(getattr(user, 'id', None))
    now = datetime.utcnow()
    if sub is None:
        return {
            'status': KonferansSubscription.STATUS_EXPIRED,
            'entitled': False,
            'days_remaining': 0,
            'expiration': None,
            'trial_end': None,
            'monthly_price': MONTHLY_PRICE_GKACH,
        }
    try:
        status = sub.compute_status(now)
        # Persist the derived status so admin listings stay truthful without a
        # scheduled job recomputing it.
        if sub.status != status:
            sub.status = status
            db.session.commit()
    except Exception:
        db.session.rollback()
        status = sub.status or KonferansSubscription.STATUS_EXPIRED
    return {
        'status': status,
        'entitled': status in (KonferansSubscription.STATUS_ACTIVE,
                              KonferansSubscription.STATUS_TRIAL),
        'days_remaining': sub.days_remaining(now) if status != KonferansSubscription.STATUS_EXPIRED else 0,
        'expiration': sub.expiration.isoformat() if sub.expiration else None,
        'trial_end': sub.trial_end.isoformat() if sub.trial_end else None,
        'monthly_price': int(sub.monthly_price_gkach or MONTHLY_PRICE_GKACH),
    }


def is_entitled(user):
    """True while the owner may run a room past the free window."""
    return bool(state_for_user(user).get('entitled'))


def pay_months(user, months, idempotency_key, room_id=None):
    """Charge Gkach for `months` and extend the subscription.

    Returns (http_status_code, payload_dict). Payload always carries `success`.
    Deduction + subscription extension + payment row commit together, so a
    failure never leaves the owner charged without the time credited.
    """
    try:
        months = int(months)
    except (TypeError, ValueError):
        return 400, {'success': False, 'error': 'Nonb mwa a dwe yon chif ant 1 ak 120.'}
    if months < MIN_MONTHS or months > MAX_MONTHS:
        return 400, {'success': False, 'error': 'Nonb mwa a dwe ant 1 ak 120.'}

    idem = str(idempotency_key or '').strip()
    if not idem:
        return 400, {'success': False, 'error': 'idempotency_key obligatwa.'}

    # Replay protection: a retried/double-clicked payment returns the original
    # result instead of charging a second time.
    try:
        previous = KonferansPayment.query.filter_by(idempotency_key=idem).first()
    except Exception:
        db.session.rollback()
        previous = None
    if previous is not None:
        return 200, {
            'success': True,
            'already_processed': True,
            'months': previous.months,
            'amount_charged': previous.amount_gkach,
            'transaction_id': previous.transaction_id,
            'message': 'Peman sa te deja trete.',
        }

    whatsapp = getattr(user, 'whatsapp', None)
    if not whatsapp:
        return 400, {'success': False, 'error': 'Ou bezwen yon WhatsApp asosye ak kont ou pou peye Gkach.'}

    now = datetime.utcnow()
    sub = get_subscription(user.id)
    if sub is None:
        sub = KonferansSubscription(
            user_id=int(user.id),
            status=KonferansSubscription.STATUS_EXPIRED,
            monthly_price_gkach=MONTHLY_PRICE_GKACH,
            trial_start=now,
            trial_end=now,  # no free month: the 45 free minutes per room is the trial
        )
        db.session.add(sub)
        db.session.flush()

    price = int(sub.monthly_price_gkach or MONTHLY_PRICE_GKACH)
    amount = price * months

    try:
        GkachService.deduct_balance(
            whatsapp, amount,
            f'KONFERANS abònman: {months} mwa x {price} Gkach',
            'konferans_subscription',
        )
    except ValidationError as ve:
        db.session.rollback()
        return 402, {
            'success': False,
            'error': str(ve),
            'insufficient_balance': True,
            'required': amount,
        }
    except Exception as e:
        db.session.rollback()
        return 500, {'success': False, 'error': f'Erè nan peman Gkach la: {e}'}

    # Extension stacks on what is left — prepaying 3 months never throws away
    # time already bought.
    base = sub.expiration if (sub.expiration and sub.expiration > now) else now
    sub.expiration = _add_months(base, months)
    sub.subscription_start = sub.subscription_start or now
    sub.status = KonferansSubscription.STATUS_ACTIVE
    sub.last_verified_at = now

    payment = KonferansPayment(
        user_id=int(user.id),
        transaction_id=f'konf-{uuid.uuid4().hex}',
        idempotency_key=idem,
        months=months,
        monthly_price_gkach=price,
        amount_gkach=amount,
        room_id=room_id,
    )
    db.session.add(payment)
    try:
        db.session.commit()
    except Exception as e:
        # Unique-constraint race on idempotency_key: the other request already
        # paid, so roll back this duplicate and report the winner's result.
        db.session.rollback()
        if 'konferans_payments' in str(e) or 'idempotency_key' in str(e) or 'UNIQUE' in str(e).upper():
            dup = KonferansPayment.query.filter_by(idempotency_key=idem).first()
            if dup is not None:
                return 200, {
                    'success': True, 'already_processed': True,
                    'months': dup.months, 'amount_charged': dup.amount_gkach,
                    'transaction_id': dup.transaction_id,
                }
        return 500, {'success': False, 'error': 'Erè nan anrejistreman peman an.'}

    try:
        new_balance = int(GkachService.get_balance(whatsapp) or 0)
    except Exception:
        new_balance = 0

    return 201, {
        'success': True,
        'message': f'Abònman KONFERANS aktif pou {months} mwa.',
        'months': months,
        'amount_charged': amount,
        'new_balance': new_balance,
        'expiration': sub.expiration.isoformat(),
        'status': KonferansSubscription.STATUS_ACTIVE,
        'entitled': True,
        'days_remaining': sub.days_remaining(now),
    }
