"""Packages, voucher generation/revocation, gateway policy sync and redemption
processing. Voucher codes are never stored: only HMAC(gateway_key, code)."""
import base64
import hashlib
import hmac
import json
import re
import secrets
import uuid
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError

from app import db
from app.wifi import subscription_service as ss
from app.wifi.models import (
    GATEWAY_ENROLLED, VOUCHER_REDEEMED, VOUCHER_REVOKED, VOUCHER_UNUSED,
    WifiAuditLog, WifiGateway, WifiGatewayKey, WifiPackage, WifiPortalConfig,
    WifiVoucher, WifiVoucherRedemption,
)
from app.wifi.vendor_service import audit, utcnow

# 31 symbols: no 0/O/1/I/L, so printed codes cannot be misread.
ALPHABET = '23456789ABCDEFGHJKMNPQRSTUVWXYZ'
CODE_LEN = 12
MAX_BATCH = 500
_HEX_COLOR = re.compile(r'^#[0-9A-Fa-f]{6}$')
_MAC = re.compile(r'^([0-9a-f]{2}:){5}[0-9a-f]{2}$')
_UID = re.compile(r'^v_[0-9a-f]{10}$')


class VoucherError(Exception):
    def __init__(self, msg, status=400):
        super().__init__(msg)
        self.status = status


# ------------------------------ code handling ------------------------------
def normalize_code(raw):
    s = re.sub(r'[\s\-]', '', str(raw or '')).upper()
    if len(s) != CODE_LEN or any(c not in ALPHABET for c in s):
        return None
    return s


def format_code(norm):
    return '-'.join(norm[i:i + 4] for i in range(0, CODE_LEN, 4))


def hash_code(key_b64, norm):
    return hmac.new(base64.b64decode(key_b64), b'v1:' + norm.encode(),
                    hashlib.sha256).hexdigest()


def gateway_key(gw):
    row = WifiGatewayKey.query.filter_by(gateway_id=gw.id).first()
    if row is None:
        row = WifiGatewayKey(gateway_id=gw.id,
                             voucher_key=base64.b64encode(secrets.token_bytes(32)).decode())
        db.session.add(row)
        db.session.flush()
    return row.voucher_key


# --------------------------------- packages ---------------------------------
def _int(v, lo, hi, field, nullable=False):
    if v is None and nullable:
        return None
    if isinstance(v, bool) or not isinstance(v, int) or not (lo <= v <= hi):
        raise VoucherError(f'{field} must be an integer between {lo} and {hi}')
    return v


def _package_values(d, partial=False):
    out = {}
    spec = {
        'price_gkach': (0, 1_000_000, False), 'duration_minutes': (1, 525_600, False),
        'data_mb': (1, 10_000_000, True), 'down_kbps': (64, 1_000_000, True),
        'up_kbps': (64, 1_000_000, True), 'max_devices': (1, 10, False),
        'voucher_valid_days': (1, 365, False),
    }
    if 'name' in d or not partial:
        name = str(d.get('name') or '').strip()
        if not (2 <= len(name) <= 80):
            raise VoucherError('name must be 2-80 characters')
        out['name'] = name
    for k, (lo, hi, nullable) in spec.items():
        if k in d:
            out[k] = _int(d[k], lo, hi, k, nullable)
        elif not partial and k in ('duration_minutes',):
            raise VoucherError('duration_minutes is required')
    if 'is_active' in d:
        if not isinstance(d['is_active'], bool):
            raise VoucherError('is_active must be true or false')
        out['is_active'] = d['is_active']
    return out


def package_dict(p):
    return {'id': p.id, 'name': p.name, 'price_gkach': p.price_gkach,
            'duration_minutes': p.duration_minutes, 'data_mb': p.data_mb,
            'down_kbps': p.down_kbps, 'up_kbps': p.up_kbps, 'max_devices': p.max_devices,
            'voucher_valid_days': p.voucher_valid_days, 'is_active': p.is_active}


def create_package(vendor, data, actor_user_id=None):
    vals = _package_values(data)
    if WifiPackage.query.filter_by(vendor_id=vendor.id, name=vals['name']).first():
        raise VoucherError('A package with this name already exists', 409)
    pkg = WifiPackage(vendor_id=vendor.id, **vals)
    db.session.add(pkg)
    audit('package.created', vendor.id, actor_user_id, vals['name'])
    db.session.commit()
    return pkg


def update_package(pkg, data, actor_user_id=None):
    vals = _package_values(data, partial=True)
    if not vals:
        raise VoucherError('nothing to change')
    if 'name' in vals and vals['name'] != pkg.name and WifiPackage.query.filter_by(
            vendor_id=pkg.vendor_id, name=vals['name']).first():
        raise VoucherError('A package with this name already exists', 409)
    for k, v in vals.items():
        setattr(pkg, k, v)
    audit('package.updated', pkg.vendor_id, actor_user_id, f'{pkg.id}:{sorted(vals)}')
    db.session.commit()
    return pkg


# ------------------------------- portal config ------------------------------
def portal_dict(cfg):
    return {'brand_name': cfg.brand_name, 'brand_color': cfg.brand_color,
            'welcome_text': cfg.welcome_text, 'voucher_enabled': cfg.voucher_enabled,
            'free_access_enabled': cfg.free_access_enabled,
            'free_package_id': cfg.free_package_id,
            'free_cooldown_hours': cfg.free_cooldown_hours}


def get_portal(vendor):
    cfg = WifiPortalConfig.query.filter_by(vendor_id=vendor.id).first()
    if cfg is None:
        cfg = WifiPortalConfig(vendor_id=vendor.id, brand_name=vendor.business_name[:60])
        db.session.add(cfg)
        db.session.flush()
    return cfg


def update_portal(vendor, data, actor_user_id=None):
    cfg = get_portal(vendor)
    if 'brand_name' in data:
        n = str(data['brand_name'] or '').strip()
        if not (2 <= len(n) <= 60) or any(ord(c) < 32 for c in n):
            raise VoucherError('brand_name must be 2-60 printable characters')
        cfg.brand_name = n
    if 'brand_color' in data:
        if not _HEX_COLOR.match(str(data['brand_color'])):
            raise VoucherError('brand_color must look like #0b6b3a')
        cfg.brand_color = data['brand_color']
    if 'welcome_text' in data:
        t = str(data['welcome_text'] or '')
        if len(t) > 240 or any(ord(c) < 32 and c not in '\n' for c in t):
            raise VoucherError('welcome_text must be at most 240 printable characters')
        cfg.welcome_text = t
    for flag in ('voucher_enabled', 'free_access_enabled'):
        if flag in data:
            if not isinstance(data[flag], bool):
                raise VoucherError(f'{flag} must be true or false')
            setattr(cfg, flag, data[flag])
    if 'free_cooldown_hours' in data:
        cfg.free_cooldown_hours = _int(data['free_cooldown_hours'], 1, 720, 'free_cooldown_hours')
    if 'free_package_id' in data:
        pid = data['free_package_id']
        if pid is not None:
            pkg = WifiPackage.query.filter_by(id=pid, vendor_id=vendor.id).first()
            if pkg is None or not pkg.is_active or pkg.price_gkach != 0:
                raise VoucherError('free_package_id must be one of your active packages with price 0')
        cfg.free_package_id = pid
    if cfg.free_access_enabled and cfg.free_package_id is None:
        raise VoucherError('free access needs a free_package_id')
    audit('portal.updated', vendor.id, actor_user_id, str(sorted(data)))
    db.session.commit()
    return cfg


# --------------------------------- vouchers ---------------------------------
def generate_vouchers(vendor, package, gateway, count, expires_in_days=None, label=None,
                      actor_user_id=None, ip=None):
    if not ss.access_state(vendor)['can_sell']:
        raise VoucherError('Subscription inactive: renew before generating vouchers', 402)
    if not package.is_active:
        raise VoucherError('Package is not active', 409)
    if gateway.status != GATEWAY_ENROLLED:
        raise VoucherError('Gateway is not active', 409)
    count = _int(count, 1, MAX_BATCH, 'count')
    valid_days = package.voucher_valid_days
    if expires_in_days is not None:
        valid_days = min(valid_days, _int(expires_in_days, 1, 365, 'expires_in_days'))
    label = (label or '')[:60] or None
    key = gateway_key(gateway)
    batch = 'b_' + secrets.token_hex(6)
    expires = utcnow() + timedelta(days=valid_days)
    codes = []
    for _ in range(count):
        for _attempt in range(5):                       # collision retry (astronomically rare)
            norm = ''.join(secrets.choice(ALPHABET) for _ in range(CODE_LEN))
            v = WifiVoucher(vendor_id=vendor.id, gateway_id=gateway.id, package_id=package.id,
                            voucher_uid='v_' + secrets.token_hex(5), code_hash=hash_code(key, norm),
                            batch_id=batch, label=label, expires_at=expires,
                            created_by_user_id=actor_user_id)
            try:
                with db.session.begin_nested():
                    db.session.add(v)
                    db.session.flush()
                codes.append(format_code(norm))
                break
            except IntegrityError:
                continue
        else:
            raise VoucherError('could not generate unique codes', 500)
    audit('voucher.generated', vendor.id, actor_user_id,
          f'batch={batch} count={count} package={package.id} gateway={gateway.gateway_uid}', ip)
    db.session.commit()
    return batch, codes, expires


def voucher_dict(v):
    return {'id': v.id, 'uid': v.voucher_uid, 'status': v.status, 'package_id': v.package_id,
            'gateway_id': v.gateway_id, 'batch_id': v.batch_id, 'label': v.label,
            'expires_at': v.expires_at.isoformat(),
            'redeemed_at': v.redeemed_at.isoformat() if v.redeemed_at else None}


def revoke_voucher(voucher, actor_user_id=None, ip=None):
    if voucher.status != VOUCHER_UNUSED:
        raise VoucherError('Only unused vouchers can be revoked', 409)
    voucher.status = VOUCHER_REVOKED
    audit('voucher.revoked', voucher.vendor_id, actor_user_id, voucher.voucher_uid, ip)
    db.session.commit()


# ------------------------------ gateway policy sync -------------------------
def _iso(dt):
    return dt.isoformat() + 'Z' if dt else None


def build_policy(gw, vendor, cursor=0, limit=1000):
    limit = max(1, min(int(limit), 1000))
    cfg = get_portal(vendor)
    key = gateway_key(gw)
    q = (WifiVoucher.query.filter(WifiVoucher.vendor_id == vendor.id,
                                  WifiVoucher.gateway_id == gw.id,
                                  WifiVoucher.status.in_((VOUCHER_UNUSED, VOUCHER_REVOKED)),
                                  WifiVoucher.id > int(cursor))
         .order_by(WifiVoucher.id).limit(limit))
    rows = q.all()
    pkgs = WifiPackage.query.filter_by(vendor_id=vendor.id, is_active=True).all()
    db.session.commit()
    return {'version': 1, 'server_time': _iso(utcnow()), 'voucher_key': key,
            'vendor': {'uid': vendor.vendor_uid, 'name': vendor.business_name},
            'access': ss.access_state(vendor), 'portal': portal_dict(cfg),
            'packages': [package_dict(p) for p in pkgs],
            'vouchers': [{'id': v.id, 'uid': v.voucher_uid, 'hash': v.code_hash,
                          'package_id': v.package_id, 'status': v.status,
                          'expires_at': _iso(v.expires_at)} for v in rows],
            'next_cursor': rows[-1].id if len(rows) == limit else None}


# ----------------------------- redemption processing ------------------------
def _dt(v):
    try:
        return datetime.fromisoformat(str(v).replace('Z', '+00:00')).replace(tzinfo=None)
    except Exception:
        return None


def apply_redemption(gw, event_id, payload):
    """Idempotent: same (gateway, event) never records twice. Tenant = gateway's vendor."""
    uid, mac = payload.get('voucher_uid'), str(payload.get('device', '')).lower()
    if not isinstance(uid, str) or not _UID.match(uid) or not _MAC.match(mac):
        audit('voucher.redemption_rejected', gw.vendor_id, None, f'bad payload gw={gw.gateway_uid}')
        return 'REJECTED'
    v = WifiVoucher.query.filter_by(vendor_id=gw.vendor_id, gateway_id=gw.id,
                                    voucher_uid=uid).first()
    if v is None:                                   # foreign / unknown voucher: never touch it
        audit('voucher.redemption_rejected', gw.vendor_id, None,
              f'unknown voucher {uid[:16]} gw={gw.gateway_uid}')
        return 'REJECTED'
    if WifiVoucherRedemption.query.filter_by(gateway_id=gw.id, event_id=event_id).first():
        return 'DUPLICATE'
    outcome, note = 'ACCEPTED', None
    if v.status == VOUCHER_REVOKED:
        outcome, note = 'CONFLICT', 'revoked before sync; offline access honored'
    elif v.status == VOUCHER_UNUSED:
        v.status = VOUCHER_REDEEMED
        v.redeemed_at = _dt(payload.get('redeemed_at')) or utcnow()
    db.session.add(WifiVoucherRedemption(
        vendor_id=gw.vendor_id, gateway_id=gw.id, voucher_id=v.id, event_id=event_id,
        device_mac=mac, redeemed_at=_dt(payload.get('redeemed_at')),
        ends_at=_dt(payload.get('ends_at')), outcome=outcome, note=note))
    return outcome
