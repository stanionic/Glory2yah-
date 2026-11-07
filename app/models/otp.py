"""
One-Time-Password (OTP) codes used to verify a WhatsApp number.

Registration no longer trusts a typed phone number: the account is created in a
*pending* state (``User.is_active = False``) and only becomes usable once the
owner proves they control the number by entering the 6-digit code the system
pushed to that number over WhatsApp.

Security notes
--------------
* Only the **hash** of the code is stored (``code_hash``), never the plaintext,
  so a database leak cannot be replayed as a valid code.
* Codes are single-use (``consumed_at``), short-lived (``expires_at``) and
  attempt-limited (``attempts``) to keep on-line guessing impractical: with 10^6
  combinations and a 5-try budget a random attacker's success chance per issued
  code is ~0.0005%.
* ``delivery_provider`` records which WhatsApp gateway actually accepted the
  message (or ``dev_fallback``), which is what makes "the OTP never arrived"
  debuggable instead of mysterious.
"""
from datetime import datetime

from app import db
from app.models.base import BaseModel


class OtpCode(BaseModel):
    """A 6-digit verification code issued to one phone number."""

    __tablename__ = 'otp_codes'

    # Purposes. A separate purpose per flow is what keeps the two codes apart:
    # issuing a login code must NOT void a pending signup code (and vice versa),
    # because both can legitimately be live for the same number at the same time.
    PURPOSE_REGISTER = 'register'
    PURPOSE_LOGIN = 'login'

    phone = db.Column(db.String(20), nullable=False, index=True)
    # Nullable: a code can be issued before/without an account (e.g. a future
    # password-reset flow keyed only on the phone number).
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)

    code_hash = db.Column(db.String(255), nullable=False)
    purpose = db.Column(db.String(20), nullable=False, default=PURPOSE_REGISTER, index=True)

    attempts = db.Column(db.Integer, default=0, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    consumed_at = db.Column(db.DateTime, nullable=True)

    delivery_provider = db.Column(db.String(30), nullable=True)
    delivered_at = db.Column(db.DateTime, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)

    # -- state helpers -----------------------------------------------------
    @property
    def is_expired(self):
        return bool(self.expires_at) and datetime.utcnow() > self.expires_at

    @property
    def is_consumed(self):
        return self.consumed_at is not None

    @property
    def is_usable(self):
        """Live: not yet used, not expired, still has attempts left."""
        from app.services.otp_service import MAX_ATTEMPTS
        return (not self.is_consumed) and (not self.is_expired) and (self.attempts or 0) < MAX_ATTEMPTS

    @classmethod
    def pending_for(cls, phone, purpose=PURPOSE_REGISTER):
        """The newest still-usable code for ``phone``, or ``None``."""
        now = datetime.utcnow()
        return (
            cls.query
            .filter(cls.phone == phone,
                    cls.purpose == purpose,
                    cls.consumed_at.is_(None),
                    cls.expires_at > now)
            .order_by(cls.created_at.desc(), cls.id.desc())
            .first()
        )

    def __repr__(self):
        return (f'<OtpCode {self.phone} purpose={self.purpose} '
                f'usable={self.is_usable} provider={self.delivery_provider}>')
