"""Global policy: defaults in code, overridable by Super Admin in wifi_settings."""
from app import db
from app.wifi.models import WifiSetting

DEFAULTS = {
    'trial_days': 3,
    'subscription_price_gkach': 1000,
    'subscription_period_days': 30,
    'offline_grace_days': 3,
    'vendor_approval_required': 0,
    'renewal_window_days': 7,     # renewal allowed when <= N days remain
    'trial_warning_hours': 24,    # warn the vendor this long before trial ends
    'max_gateways_per_vendor': 3,
    'enrollment_token_minutes': 15,
    'ticket_valid_minutes': 30,          # a paid ticket must be redeemed within this
    'purchase_refund_grace_hours': 72,   # unredeemed purchases are refunded after expiry + grace
}


def get_policy(key):
    default = DEFAULTS[key]
    row = WifiSetting.query.filter_by(key=key).first()
    if row is None:
        return default
    try:
        return int(row.value)
    except (TypeError, ValueError):
        return default


def set_policy(key, value):
    if key not in DEFAULTS:
        raise KeyError(key)
    value = int(value)
    if value < 0:
        raise ValueError('policy values cannot be negative')
    row = WifiSetting.query.filter_by(key=key).first()
    if row is None:
        row = WifiSetting(key=key, value=str(value))
        db.session.add(row)
    else:
        row.value = str(value)
    return value
