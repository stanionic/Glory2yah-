"""Persistence for the Jere Biznis offline synchronization queue."""
import json
from datetime import datetime, timezone

from app import db


def _as_utc(dt):
    """SQLite returns naive datetimes even for timezone=True columns;
    normalize to UTC-aware so comparisons never crash."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class JereBiznisSyncOperation(db.Model):
    __tablename__ = "jb_sync_operations"

    id = db.Column(db.Integer, primary_key=True)
    operation_id = db.Column(db.String(128), unique=True, nullable=False, index=True)
    admin_user_id = db.Column(db.String(128), nullable=False, index=True)
    payload = db.Column(db.Text, nullable=False)
    checksum = db.Column(db.String(128), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def payload_object(self):
        return json.loads(self.payload)


class JereBiznisLandingPage(db.Model):
    __tablename__ = "jb_landing_pages"

    id = db.Column(db.Integer, primary_key=True)
    owner_user_id = db.Column(db.String(128), nullable=False, index=True)
    business_name = db.Column(db.String(160), nullable=False)
    business_type = db.Column(db.String(40), nullable=False)
    slug = db.Column(db.String(180), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, nullable=False, default="")
    phone = db.Column(db.String(40), nullable=False, default="")
    address = db.Column(db.String(255), nullable=False, default="")
    published = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class JereBiznisAdmin(db.Model):
    """An administrator of a Jere Biznis landing page (vitrine).

    - The landing page creator is automatically its OWNER (auto-admin).
    - The OWNER can authorize CO_ADMIN users to help administer the business.
    - A user's administration of a vitrine is the pair (landing_page, user):
      every user is either owner, active co-admin, or revoked co-admin.
    """

    __tablename__ = "jb_admins"

    ROLE_OWNER = "OWNER"
    ROLE_CO_ADMIN = "CO_ADMIN"

    id = db.Column(db.Integer, primary_key=True)
    landing_page_id = db.Column(
        db.Integer,
        db.ForeignKey("jb_landing_pages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = db.Column(db.String(128), nullable=False, index=True)
    role = db.Column(db.String(20), nullable=False, default=ROLE_CO_ADMIN)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        db.UniqueConstraint(
            "landing_page_id", "user_id", name="uq_jb_admin_landing_user"
        ),
    )

    def to_dict(self):
        """Public payload for this admin row (+ resolved user display fields)."""
        from app.models.user import User

        info = {"user_id": self.user_id, "role": self.role, "active": self.active}
        info["role_label"] = "Mèt" if self.role == self.ROLE_OWNER else "Ko-Admin"
        try:
            user = (
                db.session.get(User, int(self.user_id))
                if str(self.user_id).isdigit()
                else None
            )
        except Exception:
            user = None
        if user is not None:
            info["name"] = user.name
            info["pseudo"] = user.pseudo
            info["whatsapp"] = user.whatsapp
        return info


class JereBiznisSubscription(db.Model):
    """Subscription state of a Jere Biznis admin (one row per user).

    Blueprint rules: 30-day free trial started with the first vitrine,
    500 Gkach/month, multi-month prepayment (1/3/6/12/custom), extension
    stacks on the current expiration, data is never deleted on expiration.
    """

    __tablename__ = "jb_subscriptions"

    STATUS_TRIAL = "TRIAL"
    STATUS_ACTIVE = "ACTIVE"
    STATUS_EXPIRED = "EXPIRED"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(128), nullable=False, unique=True, index=True)
    status = db.Column(db.String(30), nullable=False, default=STATUS_TRIAL)
    monthly_price_gkach = db.Column(db.Integer, nullable=False, default=500)
    trial_start = db.Column(db.DateTime(timezone=True), nullable=False)
    trial_end = db.Column(db.DateTime(timezone=True), nullable=False)
    subscription_start = db.Column(db.DateTime(timezone=True))
    expiration = db.Column(db.DateTime(timezone=True))
    last_verified_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def compute_status(self, now):
        """ACTIVE (paid) takes priority over TRIAL: a paying admin is active."""
        now = _as_utc(now)
        trial_end = _as_utc(self.trial_end)
        expiration = _as_utc(self.expiration)
        if expiration is not None and now < expiration:
            return self.STATUS_ACTIVE
        if trial_end is not None and now < trial_end:
            return self.STATUS_TRIAL
        return self.STATUS_EXPIRED

    def reminder(self, now):
        """Login reminder: shown during trial and after expiration only."""
        now = _as_utc(now)
        status = self.compute_status(now)
        if status == self.STATUS_TRIAL:
            days = max(0, (_as_utc(self.trial_end) - now).days)
        elif status == self.STATUS_ACTIVE:
            days = max(0, (_as_utc(self.expiration) - now).days)
        else:
            days = 0
        return {
            "required": status != self.STATUS_ACTIVE,
            "status": status,
            "days_remaining": days,
        }


class JereBiznisPayment(db.Model):
    """Idempotent Gkach payment record for a Jere Biznis subscription."""

    __tablename__ = "jb_payments"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(128), nullable=False, index=True)
    transaction_id = db.Column(db.String(128), unique=True, nullable=False)
    idempotency_key = db.Column(db.String(128), unique=True, nullable=False)
    months = db.Column(db.Integer, nullable=False)
    monthly_price_gkach = db.Column(db.Integer, nullable=False)
    amount_gkach = db.Column(db.Integer, nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )