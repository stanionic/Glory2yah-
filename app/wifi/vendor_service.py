"""Vendor registration, activation (starts the single free trial), suspension."""
import hashlib
import hmac
import re
from datetime import datetime, timedelta

from flask import current_app
from sqlalchemy.exc import IntegrityError

from app import db
from app.wifi.models import (
    WifiAuditLog, WifiTrial, WifiTrialLedger, WifiVendor,
    VENDOR_ACTIVE, VENDOR_PENDING, VENDOR_REJECTED, VENDOR_SUSPENDED,
)
from app.wifi.policy import get_policy


class VendorError(Exception):
    pass


def utcnow():
    return datetime.utcnow()


def identity_hash(whatsapp):
    """Stable anti-abuse fingerprint, survives account deletion/re-creation."""
    digits = re.sub(r'\D', '', whatsapp or '')
    if not digits:
        raise VendorError('A WhatsApp number is required to start a trial')
    key = current_app.config['SECRET_KEY']
    key = key.encode() if isinstance(key, str) else key
    return hmac.new(key, b'uwz-trial:' + digits.encode(), hashlib.sha256).hexdigest()


def audit(action, vendor_id=None, actor_user_id=None, detail=None, ip=None):
    db.session.add(WifiAuditLog(vendor_id=vendor_id, actor_user_id=actor_user_id,
                                action=action, detail=detail, ip=ip))


def register_vendor(user, business_name, contact_phone=None, ip=None):
    business_name = (business_name or '').strip()
    if not (2 <= len(business_name) <= 120):
        raise VendorError('Business name must be 2-120 characters')
    if not user.is_active:
        raise VendorError('Account is not active')
    if WifiVendor.query.filter_by(user_id=user.id).first():
        raise VendorError('Vendor account already exists')
    vendor = WifiVendor(user_id=user.id, business_name=business_name,
                        contact_phone=(contact_phone or '')[:30] or None,
                        status=VENDOR_PENDING)
    db.session.add(vendor)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        raise VendorError('Vendor account already exists')
    audit('vendor.registered', vendor.id, user.id, business_name, ip)
    if not get_policy('vendor_approval_required'):
        activate_vendor(vendor, actor_user_id=user.id, ip=ip)
    db.session.commit()
    return vendor


def activate_vendor(vendor, actor_user_id=None, ip=None):
    """PENDING/SUSPENDED -> ACTIVE. Starts the trial only if this person never had one."""
    if vendor.status == VENDOR_REJECTED:
        raise VendorError('Rejected vendors cannot be activated')
    was_active = vendor.status == VENDOR_ACTIVE
    vendor.status = VENDOR_ACTIVE
    vendor.suspended_reason = None
    if vendor.activated_at is None:
        vendor.activated_at = utcnow()
    trial = None
    if not was_active and WifiTrial.query.filter_by(vendor_id=vendor.id).first() is None:
        trial = _start_trial(vendor)
    audit('vendor.activated', vendor.id, actor_user_id,
          'trial_started' if trial else 'no_trial', ip)
    return trial


def _start_trial(vendor):
    """Consume the identity in the ledger and open the trial in ONE savepoint.

    The unique index on the ledger makes this race-safe: two concurrent
    activations for the same identity cannot both succeed.
    """
    ih = identity_hash(vendor.user.whatsapp)
    now = utcnow()
    try:
        with db.session.begin_nested():
            db.session.add(WifiTrialLedger(identity_hash=ih))
            trial = WifiTrial(vendor_id=vendor.id, started_at=now,
                              expires_at=now + timedelta(days=get_policy('trial_days')))
            db.session.add(trial)
            db.session.flush()
    except IntegrityError:
        return None  # trial already consumed by this identity
    return trial


def suspend_vendor(vendor, reason, actor_user_id=None, ip=None):
    vendor.status = VENDOR_SUSPENDED
    vendor.suspended_reason = (reason or '')[:255] or None
    audit('vendor.suspended', vendor.id, actor_user_id, reason, ip)


def reject_vendor(vendor, reason, actor_user_id=None, ip=None):
    if vendor.status == VENDOR_ACTIVE:
        raise VendorError('Suspend an active vendor instead of rejecting')
    vendor.status = VENDOR_REJECTED
    vendor.suspended_reason = (reason or '')[:255] or None
    audit('vendor.rejected', vendor.id, actor_user_id, reason, ip)


def trial_status(vendor):
    trial = WifiTrial.query.filter_by(vendor_id=vendor.id).first()
    if trial is None:
        return {'state': 'NONE'}
    remaining = trial.expires_at - utcnow()
    if remaining.total_seconds() <= 0:
        return {'state': 'EXPIRED', 'expires_at': trial.expires_at.isoformat()}
    return {'state': 'ACTIVE', 'expires_at': trial.expires_at.isoformat(),
            'seconds_remaining': int(remaining.total_seconds())}
