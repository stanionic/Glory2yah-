"""Signed offline licenses + gateway clock monitoring + lapse notifications.

The license is signed with the cloud's PRIVATE key (never leaves the server); the
gateway holds only the public key. It is re-issued on every heartbeat, so a
renewal reaches an online gateway within one cycle. The signed ``iat`` is also a
floor for the gateway's trusted time (rollback protection).
"""
import base64
import json
import secrets
import time
from datetime import timezone

from sqlalchemy import func

from app import db
from app.wifi import signing
from app.wifi import subscription_service as ss
from app.wifi.models import (GATEWAY_ENROLLED, VENDOR_ACTIVE, WifiSubscription, WifiTrial)
from app.wifi.policy import get_policy
from app.wifi.vendor_service import audit

_BAD_STATES = ('GRACE', 'EXPIRED', 'SUSPENDED', 'NO_PLAN')
_MESSAGES = {
    'GRACE': ('Abònman Wi-Fi ou ekspire', 'Peryòd gras la kòmanse. Renouvle abònman an pou kontinye vann nouvo fòfè.'),
    'EXPIRED': ('Abònman Wi-Fi ou fini', 'Nouvo vant ak aktivasyon yo sispann. Kliyan ki deja peye yo kontinye. Renouvle pou rekòmanse.'),
    'SUSPENDED': ('Kont Wi-Fi ou sispann', 'Kontakte administratè a. Kliyan ki deja peye yo pa afekte.'),
    'NO_PLAN': ('Pa gen plan Wi-Fi aktif', 'Abònman pou ka vann nouvo fòfè.'),
}


def _b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b'=').decode()


def _epoch(dt):
    return None if dt is None else int(dt.replace(tzinfo=timezone.utc).timestamp())


def issue_license(gw, vendor):
    trial = WifiTrial.query.filter_by(vendor_id=vendor.id).first()
    sub_end = db.session.query(func.max(WifiSubscription.period_end)).filter_by(
        vendor_id=vendor.id).scalar()
    ok = vendor.status == VENDOR_ACTIVE and gw.status == GATEWAY_ENROLLED
    payload = {'v': 1, 'k': 'license', 'lid': 'lc_' + secrets.token_hex(8),
               'vendor': vendor.vendor_uid, 'gw': gw.gateway_uid, 'iat': int(time.time()),
               'trial_exp': _epoch(trial.expires_at) if trial else None,
               'sub_exp': _epoch(sub_end), 'eff': _epoch(ss.effective_until(vendor)),
               'grace': get_policy('offline_grace_days'), 'status': 'ACTIVE' if ok else 'SUSPENDED'}
    body = _b64u(json.dumps(payload, separators=(',', ':'), sort_keys=True).encode())
    return body + '.' + _b64u(signing.sign_bytes(body.encode()))


def safe_issue(gw, vendor):
    """A missing/invalid signing key must never break heartbeats."""
    try:
        return issue_license(gw, vendor)
    except signing.SigningKeyMissing:
        return None


def record_clock(gw, clock):
    """Store the gateway's self-reported clock health (monitoring only, never trusted)."""
    if not isinstance(clock, dict):
        return
    skew, rb = clock.get('skew_s'), clock.get('rollbacks')
    if isinstance(skew, int) and not isinstance(skew, bool) and abs(skew) < 10 ** 9:
        gw.last_clock_skew_s = skew
    if isinstance(rb, int) and not isinstance(rb, bool) and 0 <= rb < 10 ** 6:
        gw.clock_rollbacks = rb


def track_state(gw, vendor):
    """Notify the vendor ONCE per transition into (or out of) a lapsed state."""
    state = ss.access_state(vendor)['state']
    coarse = state if state in _BAD_STATES else 'OK'
    prev = gw.last_license_state
    if prev == coarse:
        return None
    gw.last_license_state = coarse
    if coarse in _MESSAGES:
        ss._notify(vendor, *_MESSAGES[coarse])
    elif prev in _MESSAGES:
        ss._notify(vendor, 'Sèvis Wi-Fi ou retabli', 'Abònman an aktif ankò: ou ka vann nouvo fòfè.')
    audit('gateway.license_state', vendor.id, None, f'{gw.gateway_uid} {prev}->{coarse}')
    return coarse


def apply_gateway_event(gw, event_id, payload):
    """Audit trail for clock tampering reported by a gateway."""
    if payload.get('kind') == 'clock_rollback':
        d = payload.get('delta_s')
        if isinstance(d, int) and not isinstance(d, bool) and 0 <= d < 10 ** 9:
            audit('gateway.clock_rollback', gw.vendor_id, None, f'{gw.gateway_uid} delta={d}s')
            return 'LOGGED'
    return 'IGNORED'
