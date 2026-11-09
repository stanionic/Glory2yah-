"""
OTP issue / delivery / verification for WhatsApp number ownership checks.

Used by registration: the visitor supplies a WhatsApp number, we create a
*pending* account, push a 6-digit code to that number through the existing
provider chain (:mod:`app.services.notification_service`) and only activate the
account once the code comes back.

Why the code is hashed
----------------------
An OTP is a short-lived secret, but "short-lived" is not an excuse to store it
in the clear: the row outlives the code (it keeps ``attempts`` for lockout
accounting), and a plain-text column turns a read-only DB leak into a live
account-takeover window. ``werkzeug``'s salted hash is the same primitive
already used for passwords, so this costs nothing extra.

Delivery reality check
----------------------
``send_code()`` skips CallMeBot because its API key is bound to one
pre-registered number. The remaining provider chain tries UltraMsg first, then
Meta Cloud API and the configured webhook. Callers must treat ``None`` as "not
delivered" rather than success — see :func:`dev_fallback_allowed` for the
local-development escape hatch.
"""
import logging
import os
import re
import secrets
from datetime import datetime, timedelta

from flask import current_app
from werkzeug.security import check_password_hash, generate_password_hash

from app import db
from app.models.otp import OtpCode

logger = logging.getLogger(__name__)

OTP_LENGTH = 6
OTP_TTL = timedelta(minutes=10)
MAX_ATTEMPTS = 5
RESEND_COOLDOWN = timedelta(seconds=45)

# Stable result tokens so routes can branch on meaning, not on strings.
OK = 'ok'
WRONG = 'wrong'
EXPIRED = 'expired'
LOCKED = 'locked'
MISSING = 'missing'


def normalize_phone(raw):
    """Normalize a phone number to the E.164-like format used by User.whatsapp."""
    if not raw:
        return ''
    digits = ''.join(c for c in str(raw) if c.isdigit())
    return '+' + digits if digits else ''


def phone_variants(raw):
    """Return canonical and legacy digits-only forms for existing OTP rows."""
    normalized = normalize_phone(raw)
    if not normalized:
        return ()
    return normalized, normalized[1:]


def generate_code():
    """Uniform 6-digit code from a CSPRNG (never ``random``)."""
    return f'{secrets.randbelow(10 ** OTP_LENGTH):0{OTP_LENGTH}d}'


def dev_fallback_allowed():
    """True only on a real local dev box, where the code may be logged.

    A code is exposed only when Flask debug mode is enabled on a non-production,
    non-Render environment. Missing app context fails closed.
    """
    try:
        if any((os.environ.get(name) or '').strip()
               for name in ('RENDER', 'RENDER_SERVICE_ID', 'RENDER_EXTERNAL_URL')):
            return False
        port = (os.environ.get('PORT') or '').strip()
        if port and port != '5000':
            return False
        if (os.environ.get('FLASK_ENV') or '').strip().lower() == 'production':
            return False
        return current_app.debug
    except RuntimeError:
        return False


def _build_message(code):
    mins = int(OTP_TTL.total_seconds() // 60)
    # The link is built from the canonical site URL rather than url_for(_external=True):
    # this message leaves the process, and on Render the request Host header is the
    # *.onrender.com domain - a recipient should never be sent that.
    try:
        from app.utils.site_url import absolute_url
        link = absolute_url('/auth/verify')
    except Exception:
        link = ''
    text = (
        f"🔐 Glory2YahPub - Kòd verifikasyon ou: {code}\n"
        f"Antre kòd 6 chif sa a pou aktive kont ou. Li ekspire nan {mins} minit.\n"
        f"Pa pataje kòd sa a ak pèsonn."
    )
    if link:
        text += f"\n\nPaj verifikasyon an: {link}"
    return text


def issue(phone, user_id=None, purpose=OtpCode.PURPOSE_REGISTER, ip_address=None):
    """Create (and return) a fresh pending code, voiding earlier ones.

    Superseding old rows instead of deleting them keeps the audit trail while
    guaranteeing only one code can ever validate for a number at a time -
    otherwise a user who tapped "resend" three times would hold three live
    codes and an attacker would get three times the guessing budget.
    """
    phone = normalize_phone(phone)
    if not phone:
        raise ValueError('issue() needs a phone number')

    now = datetime.utcnow()
    stale = OtpCode.query.filter(
        OtpCode.phone.in_(phone_variants(phone)),
        OtpCode.purpose == purpose,
        OtpCode.consumed_at.is_(None),
        OtpCode.expires_at > now,
    ).all()

    for row in stale:
        row.expires_at = now  # immediately unusable

    code = generate_code()
    otp = OtpCode(
        phone=phone,
        user_id=user_id,
        code_hash=generate_password_hash(code),
        purpose=purpose,
        attempts=0,
        expires_at=now + OTP_TTL,
        ip_address=ip_address,
    )
    db.session.add(otp)
    db.session.commit()

    return otp, code


def send_code(otp, code):
    """Push ``code`` to ``otp.phone``. Returns the provider name, or ``None``.

    A ``None`` return means *no* gateway delivered it. CallMeBot is skipped
    because its API key is bound to one pre-registered number.
    In local debug we log the code so the flow stays testable; in production we
    log only the failure, never the secret.
    """
    phone = normalize_phone(otp.phone)
    if not phone:
        return None

    provider = None
    try:
        from app.services.notification_service import _send_whatsapp_alert
        provider = _send_whatsapp_alert(
            _build_message(code),
            phone[1:],
        )
    except Exception as exc:  # a broken gateway must not break registration
        logger.error('OTP delivery raised for %s: %s', phone, exc)
        provider = None

    if provider:
        otp.delivery_provider = provider
        otp.delivered_at = datetime.utcnow()
        db.session.commit()
        logger.info('OTP delivered to %s via %s', phone, provider)
        return provider

    if dev_fallback_allowed():
        # Local development only: no gateway can reach this number, so surface
        # the code in the console to keep the flow testable end-to-end.
        otp.delivery_provider = 'dev_fallback'
        db.session.commit()
        logger.warning('No WhatsApp provider delivered the OTP; using local debug fallback.')
        return 'dev_fallback'

    logger.warning(
        'OTP for %s was NOT delivered: configure ULTRAMSG_* (preferred), '
        'WHATSAPP_CLOUD_*, or WHATSAPP_ALERT_WEBHOOK_URL. CallMeBot is not '
        'used for OTP delivery because it is bound to one pre-registered line.',
        phone,
    )
    return None


def issue_and_send(phone, user_id=None, purpose=OtpCode.PURPOSE_REGISTER, ip_address=None):
    """``issue`` + ``send_code``. Returns ``(otp, delivered_via)``.

    The plaintext code is intentionally *not* returned - the caller has no
    business handling it once delivery was attempted.
    """
    otp, code = issue(phone, user_id=user_id, purpose=purpose, ip_address=ip_address)
    delivered_via = send_code(otp, code)
    if delivered_via == 'dev_fallback':
        otp.dev_code = code
    return otp, delivered_via


def resend_wait(phone, purpose=OtpCode.PURPOSE_REGISTER):
    """Seconds the user must still wait before another code, ``0`` if free."""
    phones = phone_variants(phone)
    last = (
        OtpCode.query.filter(OtpCode.phone.in_(phones), OtpCode.purpose == purpose)
        .order_by(OtpCode.created_at.desc(), OtpCode.id.desc())
        .first()
    )
    if not last or not last.created_at:
        return 0
    elapsed = datetime.utcnow() - last.created_at
    remaining = (RESEND_COOLDOWN - elapsed).total_seconds()
    return int(remaining) if remaining > 0 else 0


def has_history(phone, user_id=None, purpose=OtpCode.PURPOSE_REGISTER):
    """Was any code ever issued for this number/account?

    Used by the login route to tell "account is pending phone verification"
    apart from "an administrator disabled this legacy account" - the first has
    an OTP row, the second does not.

    """
    phones = phone_variants(phone)
    q = OtpCode.query.filter_by(purpose=purpose)
    if user_id is not None:
        q = q.filter(db.or_(OtpCode.user_id == user_id,
                            OtpCode.phone.in_(phones)))
    else:
        q = q.filter(OtpCode.phone.in_(phones))
    return q.first() is not None


def verify(phone, raw_code, purpose=OtpCode.PURPOSE_REGISTER):
    """Check a submitted code. Returns ``(status, otp_row)``.

    Statuses: ``OK`` accepted, ``WRONG`` mismatch (attempt counted),
    ``EXPIRED`` nothing live to check, ``LOCKED`` attempt budget spent,
    ``MISSING`` the visitor submitted nothing.
    """
    phone = normalize_phone(phone)
    candidate = re.sub(r'\D', '', raw_code or '')

    newest_any = (
        OtpCode.query.filter(
            OtpCode.phone.in_(phone_variants(phone)),
            OtpCode.purpose == purpose,
        )
        .order_by(OtpCode.created_at.desc(), OtpCode.id.desc())
        .first()
    )

    if not candidate:
        return MISSING, None

    otp = OtpCode.pending_for(phone, purpose)
    if otp is None:
        # Either nothing was ever issued, or the last one expired / was spent.
        if newest_any is None:
            return MISSING, None
        return EXPIRED, newest_any

    if (otp.attempts or 0) >= MAX_ATTEMPTS:
        return LOCKED, otp

    otp.attempts = (otp.attempts or 0) + 1

    if check_password_hash(otp.code_hash, candidate):
        otp.consumed_at = datetime.utcnow()
        db.session.commit()
        return OK, otp

    # Spent the last allowed attempt on a wrong answer: retire this code now so
    # the row cannot be re-tried after a page refresh.
    if otp.attempts >= MAX_ATTEMPTS:
        otp.expires_at = datetime.utcnow()
    db.session.commit()
    return WRONG, otp


def state(phone, purpose=OtpCode.PURPOSE_REGISTER):
    """Non-secret diagnostics for the verify page.

    Deliberately exposes only what the UI needs (delivery channel, time left,
    attempts budget) - never the code, its hash, nor any expiry oracle beyond the
    countdown the user is already being given.
    """
    phones = phone_variants(phone)
    newest = (
        OtpCode.query.filter(
            OtpCode.phone.in_(phones),
            OtpCode.purpose == purpose,
        )
        .order_by(OtpCode.created_at.desc(), OtpCode.id.desc())
        .first()
    )

    if newest is None:
        return {'exists': False, 'usable': False, 'provider': None,
                'attempts_left': MAX_ATTEMPTS, 'resend_in': 0}

    return {
        'exists': True,
        'usable': newest.is_usable,
        'expired': bool(newest.is_expired or newest.is_consumed),
        'provider': newest.delivery_provider,
        'attempts_left': max(0, MAX_ATTEMPTS - (newest.attempts or 0)),
        'resend_in': resend_wait(newest.phone, purpose),
    }


def purge_expired(max_age_days=7):
    """Housekeeping: drop codes older than ``max_age_days`` (all terminal)."""
    cutoff = datetime.utcnow() - timedelta(days=max_age_days)
    deleted = OtpCode.query.filter(OtpCode.created_at < cutoff).delete()
    db.session.commit()
    if deleted:
        logger.info('Purged %s OTP rows older than %s days', deleted, max_age_days)
    return deleted
