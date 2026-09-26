import json
from datetime import datetime, timezone, timedelta
from ..extensions import db
from ..models import Subscription, Payment, AuditLog
from .billing import amount_for_months, next_expiration

def create_trial(institution_id, price, days):
    now=datetime.now(timezone.utc)
    return Subscription(
        institution_id=institution_id,status="TRIAL",
        monthly_price_gkach=price,trial_start=now,
        trial_end=now+timedelta(days=days))

def apply_payment(sub, institution_id, tx, idem, months, actor):
    now=datetime.now(timezone.utc)
    amount=amount_for_months(months,sub.monthly_price_gkach)
    old=sub.expiration
    sub.expiration=next_expiration(now,sub.trial_end,sub.expiration,months)
    sub.subscription_start=sub.subscription_start or now
    sub.status="ACTIVE"
    sub.last_verified_at=now
    payment=Payment(
        institution_id=institution_id,transaction_id=tx,idempotency_key=idem,
        months=months,monthly_price_gkach=sub.monthly_price_gkach,amount_gkach=amount)
    db.session.add(payment)
    db.session.add(AuditLog(
        institution_id=institution_id,event_type="GKACH_PAYMENT_SUCCESS",
        actor_user_id=actor,
        metadata_json=json.dumps({
            "months":months,"amount_gkach":amount,
            "old_expiration":old.isoformat() if old else None,
            "new_expiration":sub.expiration.isoformat()})))
    return payment
