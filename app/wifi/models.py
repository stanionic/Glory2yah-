"""Data model for the UWZ module. All tables are prefixed ``wifi_``.

Every tenant-owned table inherits TenantScoped: ``vendor_id`` is NOT NULL,
indexed, and checked by the flush guard in tenancy.py.
"""
import secrets
from datetime import datetime

from sqlalchemy import UniqueConstraint

from app import db
from app.models.base import BaseModel

VENDOR_PENDING = 'PENDING'      # waiting for admin approval (if enabled)
VENDOR_ACTIVE = 'ACTIVE'
VENDOR_SUSPENDED = 'SUSPENDED'
VENDOR_REJECTED = 'REJECTED'
VENDOR_STATUSES = (VENDOR_PENDING, VENDOR_ACTIVE, VENDOR_SUSPENDED, VENDOR_REJECTED)


def _new_vendor_uid():
    return 'UWZ-' + secrets.token_hex(5).upper()


class TenantScoped:
    """Mixin marking a model as owned by exactly one vendor."""
    __tenant_scoped__ = True



class WifiVendor(BaseModel):
    __tablename__ = 'wifi_vendors'

    vendor_uid = db.Column(db.String(20), unique=True, nullable=False,
                           index=True, default=_new_vendor_uid)
    # One vendor account per Glory2YahPub user (no second auth system).
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'),
                        unique=True, nullable=False, index=True)
    business_name = db.Column(db.String(120), nullable=False)
    contact_phone = db.Column(db.String(30))
    status = db.Column(db.String(20), nullable=False, default=VENDOR_PENDING, index=True)
    activated_at = db.Column(db.DateTime)
    suspended_reason = db.Column(db.String(255))

    user = db.relationship('User', backref=db.backref('wifi_vendor', uselist=False))

    def to_dict(self, **_):
        return {
            'vendor_uid': self.vendor_uid,
            'business_name': self.business_name,
            'status': self.status,
            'activated_at': self.activated_at.isoformat() if self.activated_at else None,
        }


class WifiTrialLedger(BaseModel):
    """Anti-abuse register, deliberately NOT tied to the vendor/user rows.

    ``identity_hash`` is an HMAC of the normalized WhatsApp number. It survives
    deletion of the vendor or the user account, so re-registering (or
    reinstalling) can never grant a second free trial.
    """
    __tablename__ = 'wifi_trial_ledger'

    identity_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)


class WifiTrial(TenantScoped, BaseModel):
    """The trial window of one vendor (one row per vendor, at most)."""
    __tablename__ = 'wifi_trials'

    vendor_id = db.Column(db.Integer, db.ForeignKey('wifi_vendors.id'),
                          nullable=False, unique=True, index=True)
    started_at = db.Column(db.DateTime, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    warned_at = db.Column(db.DateTime)   # pre-expiry notification sent


class WifiSetting(BaseModel):
    """Global network policy editable by Super Admin (key/value)."""
    __tablename__ = 'wifi_settings'

    key = db.Column(db.String(64), unique=True, nullable=False, index=True)
    value = db.Column(db.String(255), nullable=False)


class WifiAuditLog(BaseModel):
    __tablename__ = 'wifi_audit_logs'

    vendor_id = db.Column(db.Integer, db.ForeignKey('wifi_vendors.id'), index=True)
    actor_user_id = db.Column(db.Integer, index=True)
    action = db.Column(db.String(60), nullable=False, index=True)
    detail = db.Column(db.Text)
    ip = db.Column(db.String(45))


class WifiSubscription(TenantScoped, BaseModel):
    """One paid 30-day period. Created ONLY after the GKach debit succeeded."""
    __tablename__ = 'wifi_subscriptions'
    __table_args__ = (
        # A period start can be billed once per vendor, whatever the race.
        UniqueConstraint('vendor_id', 'period_start', name='uq_wifi_sub_vendor_period'),
    )

    vendor_id = db.Column(db.Integer, db.ForeignKey('wifi_vendors.id'),
                          nullable=False, index=True)
    period_start = db.Column(db.DateTime, nullable=False)
    period_end = db.Column(db.DateTime, nullable=False, index=True)
    amount_gkach = db.Column(db.Integer, nullable=False)
    transaction_id = db.Column(db.Integer, db.ForeignKey('wifi_subscription_transactions.id'))


class WifiSubscriptionTransaction(TenantScoped, BaseModel):
    """Every renewal attempt (success or failure) for audit/inspection."""
    __tablename__ = 'wifi_subscription_transactions'
    __table_args__ = (
        UniqueConstraint('vendor_id', 'idempotency_key', name='uq_wifi_subtx_vendor_key'),
    )

    vendor_id = db.Column(db.Integer, db.ForeignKey('wifi_vendors.id'),
                          nullable=False, index=True)
    idempotency_key = db.Column(db.String(64))          # NULL allowed (failures)
    amount_gkach = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, index=True)  # COMPLETED | FAILED
    ledger_transaction_id = db.Column(db.String(36), index=True)   # gkach_transactions.transaction_id
    failure_reason = db.Column(db.String(255))


GATEWAY_ENROLLED = 'ENROLLED'
GATEWAY_SUSPENDED = 'SUSPENDED'
GATEWAY_REVOKED = 'REVOKED'


class WifiGateway(TenantScoped, BaseModel):
    """A local gateway. It holds its own private key; we store only the public key."""
    __tablename__ = 'wifi_gateways'

    vendor_id = db.Column(db.Integer, db.ForeignKey('wifi_vendors.id'),
                          nullable=False, index=True)
    gateway_uid = db.Column(db.String(24), unique=True, nullable=False, index=True)
    name = db.Column(db.String(80), nullable=False)
    status = db.Column(db.String(20), nullable=False, default=GATEWAY_ENROLLED, index=True)
    public_key = db.Column(db.String(64), unique=True, nullable=False)   # Ed25519, base64
    enrolled_at = db.Column(db.DateTime, nullable=False)
    last_seen_at = db.Column(db.DateTime, index=True)
    last_ip = db.Column(db.String(45))
    agent_version = db.Column(db.String(32))
    portal_url = db.Column(db.String(200))      # LAN URL of the gateway's captive portal
    last_clock_skew_s = db.Column(db.Integer)   # device wall clock minus trusted time (monitoring)
    clock_rollbacks = db.Column(db.Integer, nullable=False, default=0)
    last_license_state = db.Column(db.String(12))   # for notify-once-per-transition


class WifiGatewayEnrollment(TenantScoped, BaseModel):
    """One-time enrollment token. Only its SHA-256 is stored."""
    __tablename__ = 'wifi_gateway_enrollments'

    vendor_id = db.Column(db.Integer, db.ForeignKey('wifi_vendors.id'),
                          nullable=False, index=True)
    token_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    name = db.Column(db.String(80), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime)
    gateway_id = db.Column(db.Integer, db.ForeignKey('wifi_gateways.id'))
    created_by_user_id = db.Column(db.Integer)


class WifiGatewayNonce(BaseModel):
    """Replay protection: a (gateway, nonce) pair is accepted once."""
    __tablename__ = 'wifi_gateway_nonces'
    __table_args__ = (UniqueConstraint('gateway_id', 'nonce', name='uq_wifi_nonce'),)

    gateway_id = db.Column(db.Integer, db.ForeignKey('wifi_gateways.id'),
                           nullable=False, index=True)
    nonce = db.Column(db.String(64), nullable=False)


class WifiOfflineEvent(TenantScoped, BaseModel):
    """Event produced offline by a gateway, received on sync (idempotent)."""
    __tablename__ = 'wifi_offline_events'
    __table_args__ = (UniqueConstraint('gateway_id', 'event_id', name='uq_wifi_event'),)

    vendor_id = db.Column(db.Integer, db.ForeignKey('wifi_vendors.id'),
                          nullable=False, index=True)
    gateway_id = db.Column(db.Integer, db.ForeignKey('wifi_gateways.id'),
                           nullable=False, index=True)
    event_id = db.Column(db.String(36), nullable=False)
    seq = db.Column(db.Integer, nullable=False)
    event_type = db.Column(db.String(40), nullable=False, index=True)
    payload = db.Column(db.Text, nullable=False)
    gateway_created_at = db.Column(db.DateTime)
    processed_at = db.Column(db.DateTime)     # set by later phases (billing/usage)


class WifiSyncLog(TenantScoped, BaseModel):
    __tablename__ = 'wifi_sync_logs'

    vendor_id = db.Column(db.Integer, db.ForeignKey('wifi_vendors.id'),
                          nullable=False, index=True)
    gateway_id = db.Column(db.Integer, db.ForeignKey('wifi_gateways.id'),
                           nullable=False, index=True)
    received = db.Column(db.Integer, nullable=False, default=0)
    accepted = db.Column(db.Integer, nullable=False, default=0)
    duplicates = db.Column(db.Integer, nullable=False, default=0)
    rejected = db.Column(db.Integer, nullable=False, default=0)


ROUTER_CAPABILITIES = ('info', 'wifi_read', 'wifi_config', 'clients', 'dhcp_leases',
                       'dhcp_config', 'bandwidth', 'diagnostics')


class WifiRouter(TenantScoped, BaseModel):
    """Router/AP seen by a gateway. Inventory snapshot; holds NO credentials."""
    __tablename__ = 'wifi_routers'
    __table_args__ = (UniqueConstraint('gateway_id', 'router_ref', name='uq_wifi_router_ref'),)

    vendor_id = db.Column(db.Integer, db.ForeignKey('wifi_vendors.id'),
                          nullable=False, index=True)
    gateway_id = db.Column(db.Integer, db.ForeignKey('wifi_gateways.id'),
                           nullable=False, index=True)
    router_ref = db.Column(db.String(40), nullable=False)
    kind = db.Column(db.String(20), nullable=False)
    vendor_label = db.Column(db.String(40))
    model = db.Column(db.String(80))
    firmware = db.Column(db.String(80))
    status = db.Column(db.String(20), nullable=False, index=True)  # ONLINE|OFFLINE|UNSUPPORTED
    support_level = db.Column(db.String(20), nullable=False)
    hardware_verified = db.Column(db.Boolean, nullable=False, default=False)
    capabilities = db.Column(db.Text, nullable=False, default='[]')
    last_error = db.Column(db.String(200))
    last_report_at = db.Column(db.DateTime, nullable=False)


# ----------------------------- Phase 6: packages / vouchers / portal ---------
VOUCHER_UNUSED = 'UNUSED'
VOUCHER_REDEEMED = 'REDEEMED'
VOUCHER_REVOKED = 'REVOKED'


class WifiPackage(TenantScoped, BaseModel):
    """An Internet package sold (or given) by one vendor."""
    __tablename__ = 'wifi_packages'
    __table_args__ = (UniqueConstraint('vendor_id', 'name', name='uq_wifi_package_name'),)

    vendor_id = db.Column(db.Integer, db.ForeignKey('wifi_vendors.id'),
                          nullable=False, index=True)
    name = db.Column(db.String(80), nullable=False)
    price_gkach = db.Column(db.Integer, nullable=False, default=0)   # 0 = free
    duration_minutes = db.Column(db.Integer, nullable=False)
    data_mb = db.Column(db.Integer)                 # NULL = unlimited
    down_kbps = db.Column(db.Integer)               # NULL = unlimited
    up_kbps = db.Column(db.Integer)
    max_devices = db.Column(db.Integer, nullable=False, default=1)
    voucher_valid_days = db.Column(db.Integer, nullable=False, default=30)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)


class WifiPortalConfig(TenantScoped, BaseModel):
    """Branding and access modes of one vendor's captive portal."""
    __tablename__ = 'wifi_portal_configs'

    vendor_id = db.Column(db.Integer, db.ForeignKey('wifi_vendors.id'),
                          nullable=False, unique=True, index=True)
    brand_name = db.Column(db.String(60), nullable=False)
    brand_color = db.Column(db.String(7), nullable=False, default='#0b6b3a')
    welcome_text = db.Column(db.String(240), nullable=False, default='')
    voucher_enabled = db.Column(db.Boolean, nullable=False, default=True)
    free_access_enabled = db.Column(db.Boolean, nullable=False, default=False)
    free_package_id = db.Column(db.Integer, db.ForeignKey('wifi_packages.id'))
    free_cooldown_hours = db.Column(db.Integer, nullable=False, default=24)


class WifiGatewayKey(BaseModel):
    """Per-gateway secret used to HMAC voucher codes (bound to ONE gateway)."""
    __tablename__ = 'wifi_gateway_keys'

    gateway_id = db.Column(db.Integer, db.ForeignKey('wifi_gateways.id'),
                           nullable=False, unique=True, index=True)
    voucher_key = db.Column(db.String(64), nullable=False)   # base64 of 32 random bytes


class WifiVoucher(TenantScoped, BaseModel):
    """Only a keyed hash of the code is stored; the plaintext is shown once."""
    __tablename__ = 'wifi_vouchers'

    vendor_id = db.Column(db.Integer, db.ForeignKey('wifi_vendors.id'),
                          nullable=False, index=True)
    gateway_id = db.Column(db.Integer, db.ForeignKey('wifi_gateways.id'),
                           nullable=False, index=True)
    package_id = db.Column(db.Integer, db.ForeignKey('wifi_packages.id'),
                           nullable=False, index=True)
    voucher_uid = db.Column(db.String(16), unique=True, nullable=False, index=True)
    code_hash = db.Column(db.String(64), unique=True, nullable=False)
    status = db.Column(db.String(12), nullable=False, default=VOUCHER_UNUSED, index=True)
    batch_id = db.Column(db.String(16), index=True)
    label = db.Column(db.String(60))
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    redeemed_at = db.Column(db.DateTime)
    created_by_user_id = db.Column(db.Integer)


class WifiVoucherRedemption(TenantScoped, BaseModel):
    """One row per device that used a voucher (history + idempotency by event)."""
    __tablename__ = 'wifi_voucher_redemptions'
    __table_args__ = (UniqueConstraint('gateway_id', 'event_id', name='uq_wifi_redeem_event'),)

    vendor_id = db.Column(db.Integer, db.ForeignKey('wifi_vendors.id'),
                          nullable=False, index=True)
    gateway_id = db.Column(db.Integer, db.ForeignKey('wifi_gateways.id'), nullable=False)
    voucher_id = db.Column(db.Integer, db.ForeignKey('wifi_vouchers.id'),
                           nullable=False, index=True)
    event_id = db.Column(db.String(36), nullable=False)
    device_mac = db.Column(db.String(17), nullable=False)
    redeemed_at = db.Column(db.DateTime)          # gateway clock
    ends_at = db.Column(db.DateTime)
    outcome = db.Column(db.String(12), nullable=False)    # ACCEPTED | CONFLICT
    note = db.Column(db.String(120))


# ----------------------------- Phase 7: purchases / usage --------------------
PURCHASE_HELD = 'HELD'            # buyer debited, waiting for the gateway to deliver
PURCHASE_SETTLED = 'SETTLED'      # delivered -> vendor credited
PURCHASE_REFUNDED = 'REFUNDED'    # never delivered -> buyer refunded
PURCHASE_CONFLICT = 'CONFLICT'    # delivery reported AFTER the refund (needs admin review)


class WifiPurchase(TenantScoped, BaseModel):
    """A customer's GKach purchase of a package, delivered through a signed ticket."""
    __tablename__ = 'wifi_purchases'
    __table_args__ = (UniqueConstraint('buyer_user_id', 'idempotency_key',
                                       name='uq_wifi_purchase_idem'),)

    vendor_id = db.Column(db.Integer, db.ForeignKey('wifi_vendors.id'),
                          nullable=False, index=True)
    gateway_id = db.Column(db.Integer, db.ForeignKey('wifi_gateways.id'),
                          nullable=False, index=True)
    package_id = db.Column(db.Integer, db.ForeignKey('wifi_packages.id'), nullable=False)
    buyer_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    idempotency_key = db.Column(db.String(64), nullable=False)
    amount_gkach = db.Column(db.Integer, nullable=False)
    package_name = db.Column(db.String(80), nullable=False)      # snapshot at purchase time
    duration_minutes = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(12), nullable=False, default=PURCHASE_HELD, index=True)
    ticket_id = db.Column(db.String(24), unique=True, nullable=False)
    ticket = db.Column(db.Text, nullable=False)
    device_tag = db.Column(db.String(32), nullable=False)
    ticket_expires_at = db.Column(db.DateTime, nullable=False, index=True)
    ledger_transaction_id = db.Column(db.String(36))
    settled_at = db.Column(db.DateTime)
    refunded_at = db.Column(db.DateTime)


class WifiUsageRecord(TenantScoped, BaseModel):
    """Bytes used by one entitlement, reported by the gateway (idempotent by event)."""
    __tablename__ = 'wifi_usage_records'
    __table_args__ = (UniqueConstraint('gateway_id', 'event_id', name='uq_wifi_usage_event'),)

    vendor_id = db.Column(db.Integer, db.ForeignKey('wifi_vendors.id'),
                          nullable=False, index=True)
    gateway_id = db.Column(db.Integer, db.ForeignKey('wifi_gateways.id'),
                           nullable=False, index=True)
    event_id = db.Column(db.String(36), nullable=False)
    source = db.Column(db.String(10), nullable=False)            # voucher | free | purchase
    ref = db.Column(db.String(40), nullable=False, index=True)   # voucher uid / ticket id / free:<n>
    bytes_down = db.Column(db.BigInteger, nullable=False, default=0)
    bytes_up = db.Column(db.BigInteger, nullable=False, default=0)
    period_end = db.Column(db.DateTime, nullable=False, index=True)
